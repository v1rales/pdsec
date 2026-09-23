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

#: Код страны РФ для телефона (открывается при маскировании).
_PHONE_COUNTRY_CODE = "+7"
#: Разделители телефона, сохраняемые при маскировании.
_PHONE_SEPARATORS = "()- "
#: Разделители email, сохраняемые при маскировании.
_EMAIL_SEPARATORS = "@._-"
#: Разделители даты, сохраняемые при маскировании.
_DATE_SEPARATORS = "./- "


def _mask_digits(value: str, open_positions: set[int], keep: str) -> str:
    """Маскирует цифры, кроме открытых позиций; разделители из keep сохраняются.

    Общий паттерн для паспорта/карты/ИНН: собираются индексы цифр, выбираются
    открытые (первые/последние), остальные цифры → '*'.
    """
    return "".join(
        ch if ch in keep or (ch.isdigit() and i in open_positions) else "*"
        for i, ch in enumerate(value)
    )


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
    open_positions = set(digits[:2]) | set(digits[-2:])
    return _mask_digits(value, open_positions, " ")


def _mask_card(value: str) -> str:
    """Карта: '4532 0151 1283 0366' → '**** **** **** 0366' (последние 4 цифры)."""
    digits = [i for i, ch in enumerate(value) if ch.isdigit()]
    if len(digits) < 4:
        return _mask_all(value, " ")
    open_positions = set(digits[-4:])
    return _mask_digits(value, open_positions, " ")


def _mask_phone(value: str) -> str:
    """Телефон: '+7 900 123-45-67' → '+7 *** ***-**-**' (код страны открыт)."""
    # Открываем код страны независимо от разделителя после него (пробел или '(').
    if value.startswith(_PHONE_COUNTRY_CODE):
        return _PHONE_COUNTRY_CODE + _mask_all(value[len(_PHONE_COUNTRY_CODE):], _PHONE_SEPARATORS)
    return _mask_all(value, _PHONE_SEPARATORS)


def _mask_email(value: str) -> str:
    """Email: 'ivanov@mail.ru' → 'i****@****.ru' (первая буква + домен .ru)."""
    if "@" not in value:
        return _mask_all(value, _EMAIL_SEPARATORS)
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
    open_positions = set(digits[-2:])
    return _mask_digits(value, open_positions, "")


def _mask_date(value: str) -> str:
    """Дата: '15.03.1990' → '**.**.1990', '15.03.90' → '**.**.90' (год открыт).

    Год — группа из 4 цифр, если есть, иначе последняя группа из 2 цифр.
    Открывается только год; день и месяц закрываются одинаково для
    2-значного и 4-значного года.
    """
    digits = [i for i, ch in enumerate(value) if ch.isdigit()]
    if len(digits) < 4:
        return _mask_all(value, _DATE_SEPARATORS)
    # Год: 4-значная группа, если есть; иначе последняя 2-значная группа.
    year = re.search(r"\d{4}", value)
    if not year:
        year = re.search(r"\d{2}$", value)
    if year:
        open_positions = set(range(year.start(), year.end()))
        return _mask_digits(value, open_positions, _DATE_SEPARATORS)
    open_positions = set(digits[-2:])
    return _mask_digits(value, open_positions, _DATE_SEPARATORS)


def mask_span(value: str, type_: str, mask_style: str = "partial") -> str:
    """Маскирует значение спана по правилам типа и стилю маскирования.

    mask_style:
      - "partial" — текущее поведение (инициалы ФИО, открытые символы);
      - "full" — все значащие символы → *, разделители сохраняются;
      - "tokenize" — замена на плейсхолдер [TYPE].
    """
    if mask_style == "full":
        return _mask_all(value, _SEPARATORS)
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