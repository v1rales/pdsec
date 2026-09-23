"""Правила маскирования по типу ПД.

Маска соответствует эталону ТЗ Приложение A: для ФИО — инициалы,
для части типов — открытые символы (первые/последние). Разделители
(пробелы, точки, дефисы, +, @) остаются на местах.

Демаскирование идёт через vault по payload_id, поэтому маска не обязана
сохранять длину. Длина нужна только для метрики (span-based Левенштейн),
которая сравнивает с эталоном ТЗ.
"""

import re


def _mask_all(value: str, keep: str) -> str:
    """Маскирует все значащие символы, сохраняя разделители."""
    return "".join(ch if ch in keep else "*" for ch in value)


#: Разделители, сохраняемые при полном маскировании (mask_style="full").
_SEPARATORS = " .-+@(),/"


def _mask_full(value: str) -> str:
    """Полное маскирование: все значащие символы → *, разделители сохраняются."""
    return "".join(ch if ch in _SEPARATORS else "*" for ch in value)


def _mask_fio(value: str) -> str:
    """ФИО → инициалы: 'Иванов Иван Иванович' → 'И. И. И.'."""
    words = value.split()
    return " ".join(w[0].upper() + "." for w in words if w)


def _mask_passport(value: str) -> str:
    """Паспорт: '4509 123456' → '45** ****56' (первые 2 и последние 2 цифры).

    Маскируются только цифры серии/номера; буквы (например, слово-связка
    «номер») и разделители остаются на месте.
    """
    digits = [i for i, ch in enumerate(value) if ch.isdigit()]
    if len(digits) < 4:
        return _mask_all(value, " ")
    open_first = set(digits[:2])
    open_last = set(digits[-2:])
    return "".join(
        ch if not ch.isdigit() or i in open_first | open_last else "*"
        for i, ch in enumerate(value)
    )


def _mask_card(value: str) -> str:
    """Карта: '4532 0151 1283 0366' → '**** **** **** 0366' (последние 4 цифры)."""
    digits = [i for i, ch in enumerate(value) if ch.isdigit()]
    if len(digits) < 4:
        return _mask_all(value, " ")
    open_last = set(digits[-4:])
    return "".join(
        ch if ch == " " or (ch.isdigit() and i in open_last) else "*"
        for i, ch in enumerate(value)
    )


def _mask_phone(value: str) -> str:
    """Телефон: '+7 900 123-45-67' → '+7 *** ***-**-**' (код страны открыт)."""
    # Открываем '+7' (код страны) независимо от разделителя после него
    # (пробел или '('), остальные цифры маскируем.
    if value.startswith("+7"):
        return "+7" + _mask_all(value[2:], "()- ")
    return _mask_all(value, "+()- ")


def _mask_email(value: str) -> str:
    """Email: 'ivanov@mail.ru' → 'i****@****.ru' (первая буква + домен .ru)."""
    if "@" not in value:
        return _mask_all(value, "@._-")
    local, domain = value.split("@", 1)
    # Локальная часть: первая буква открыта, остальное → *.
    masked_local = local[0] + "*" * (len(local) - 1) if local else ""
    # Домен: имя маскируем, TLD (.ru) открыт.
    if "." in domain:
        name, tld = domain.rsplit(".", 1)
        masked_domain = "*" * len(name) + "." + tld
    else:
        masked_domain = "*" * len(domain)
    return masked_local + "@" + masked_domain


def _mask_inn(value: str) -> str:
    """ИНН: '500100732259' → '**********59' (последние 2 цифры)."""
    digits = [i for i, ch in enumerate(value) if ch.isdigit()]
    if len(digits) < 2:
        return _mask_all(value, "")
    open_last = set(digits[-2:])
    return "".join(
        ch if ch.isdigit() and i in open_last else "*"
        for i, ch in enumerate(value)
    )


def _mask_date(value: str) -> str:
    """Дата: '15.03.1990' → '**.**.1990', '15.03.90' → '**.**.90' (год открыт).

    Год — группа из 4 цифр, если есть, иначе последняя группа из 2 цифр.
    Открывается только год; день и месяц закрываются одинаково для
    2-значного и 4-значного года.
    """
    digits = [i for i, ch in enumerate(value) if ch.isdigit()]
    if len(digits) < 4:
        return _mask_all(value, "./- ")
    # Год: 4-значная группа, если есть; иначе последняя 2-значная группа.
    year = re.search(r"\d{4}", value)
    if not year:
        year = re.search(r"\d{2}$", value)
    if year:
        open_year = set(range(year.start(), year.end()))
        return "".join(
            ch if ch in "./- " or (ch.isdigit() and i in open_year) else "*"
            for i, ch in enumerate(value)
        )
    open_last = set(digits[-2:])
    return "".join(
        ch if ch in "./- " or (ch.isdigit() and i in open_last) else "*"
        for i, ch in enumerate(value)
    )


def mask_span(value: str, type_: str, mask_style: str = "partial") -> str:
    """Маскирует значение спана по правилам типа и стилю маскирования.

    mask_style:
      - "partial" — текущее поведение (инициалы ФИО, открытые символы);
      - "full" — все значащие символы → *, разделители сохраняются;
      - "tokenize" — замена на плейсхолдер [TYPE].
    """
    if mask_style == "full":
        return _mask_full(value)
    if mask_style == "tokenize":
        return f"[{type_.upper()}]"
    if type_ == "fio":
        return _mask_fio(value)
    if type_ == "passport":
        return _mask_passport(value)
    if type_ == "card":
        return _mask_card(value)
    if type_ == "phone":
        return _mask_phone(value)
    if type_ == "email":
        return _mask_email(value)
    if type_ == "inn":
        return _mask_inn(value)
    if type_ == "date":
        return _mask_date(value)
    # Остальные типы: все значащие → *, разделители сохраняются.
    keep = {
        "cvv": "",
        "pin": "",
        "division_code": "-",
        "license": " ",
        "city": " -",
        "country": " -",
        "address": " ,.-",
        "issuer": " ,.-",
    }.get(type_, "")
    return _mask_all(value, keep)