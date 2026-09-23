"""Генератор синтетического датасета ПД с разметкой спанов.

Смещения спанов вычисляются в момент подстановки значения в шаблон
(конкатенация с подсчётом позиций), а не парсингом готового текста.
Это независимый эталон для скорера.

Формат выходного JSON — список примеров:
    {"text": str, "spans": [{"type": str, "start": int, "end": int}], "negative": bool}

CLI: python tools/gen_dataset.py --out <path> --seed <int> --count <int>
     python tools/gen_dataset.py --out <path> --independent  # независимый датасет
"""

import argparse
import json
import os
import random
import sys

# UTF-8 для stdout/stderr (Windows-консоль по умолчанию cp1252 не выводит кириллицу).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# --- Словари и константы, согласованные с детекторами в app/detectors/ ---

# Весовые коэффициенты контрольных разрядов ИНН (как в app/detectors/inn.py).
_WEIGHTS_11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_WEIGHTS_12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)

# Допустимые коды регионов серии паспорта (как в app/detectors/passport.py).
_VALID_REGIONS = (
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19,
    22, 24, 25, 27, 28, 29, 30, 32, 34, 37, 38, 39, 40, 44, 45, 46, 48,
    50, 52, 53, 55, 56, 57, 58, 62, 64, 67, 72, 78, 91, 92,
)

# Имена и отчества (подмножество словарей app/detectors/fio.py).
_NAMES = (
    "Александр", "Алексей", "Андрей", "Анна", "Борис", "Вадим",
    "Василий", "Виктор", "Владимир", "Вячеслав", "Галина", "Геннадий",
    "Георгий", "Григорий", "Дмитрий", "Евгений", "Екатерина", "Елена",
    "Иван", "Игорь", "Илья", "Ирина", "Кирилл", "Константин",
    "Лариса", "Леонид", "Людмила", "Максим", "Марина", "Мария",
    "Михаил", "Надежда", "Наталья", "Николай", "Оксана", "Олег",
    "Ольга", "Павел", "Пётр", "Роман", "Светлана", "Сергей",
    "Степан", "Татьяна", "Фёдор", "Юлия", "Юрий", "Яков",
)
_PATRONYMICS = (
    "Александрович", "Александровна", "Алексеевич", "Алексеевна",
    "Андреевич", "Андреевна", "Борисович", "Борисовна",
    "Васильевич", "Васильевна", "Викторович", "Викторовна",
    "Владимирович", "Владимировна", "Вячеславович", "Вячеславовна",
    "Геннадьевич", "Геннадьевна", "Георгиевич", "Георгиевна",
    "Григорьевич", "Григорьевна", "Дмитриевич", "Дмитриевна",
    "Евгеньевич", "Евгеньевна", "Иванович", "Ивановна",
    "Игоревич", "Игоревна", "Ильич", "Ильинична",
    "Кириллович", "Кирилловна", "Константинович", "Константиновна",
    "Леонидович", "Леонидовна", "Максимович", "Максимовна",
    "Михайлович", "Михайловна", "Николаевич", "Николаевна",
    "Олегович", "Олеговна", "Павлович", "Павловна",
    "Петрович", "Петровна", "Романович", "Романовна",
    "Сергеевич", "Сергеевна", "Степанович", "Степановна",
    "Фёдорович", "Фёдоровна", "Юрьевич", "Юрьевна",
    "Яковлевич", "Яковлевна",
)
# Фамилии, оканчивающиеся на суффикс фамилии (морфология, как в fio.py).
_SURNAMES = (
    "Иванов", "Петров", "Сидоров", "Кузнецов", "Смирнов",
    "Васильев", "Михайлов", "Фёдоров", "Андреев", "Алексеев",
    "Николаев", "Сергеев", "Дмитриев", "Александров", "Борисов",
    "Владимиров", "Григорьев", "Егоров", "Козлов", "Морозов",
    "Волков", "Соколов", "Павлов", "Семёнов", "Голубев",
    "Виноградов", "Богданов", "Орлов", "Крылов", "Соловьёв",
)

# Города (подмножество словаря app/detectors/city.py).
_CITIES = (
    "Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург",
    "Казань", "Нижний Новгород", "Челябинск", "Самара", "Омск",
    "Ростов-на-Дону", "Уфа", "Красноярск", "Воронеж", "Пермь",
    "Волгоград", "Краснодар", "Саратов", "Тюмень", "Тольятти",
    "Ижевск", "Барнаул", "Ульяновск", "Иркутск", "Хабаровск",
    "Ярославль", "Владивосток", "Махачкала", "Томск", "Оренбург",
    "Кемерово", "Новокузнецк", "Рязань", "Астрахань",
    "Набережные Челны", "Пенза", "Липецк", "Киров", "Чебоксары",
    "Тула", "Калининград", "Курск", "Севастополь", "Сочи",
    "Ставрополь", "Улан-Удэ", "Тверь", "Магнитогорск", "Иваново",
    "Брянск", "Белгород", "Сургут", "Владимир", "Нижний Тагил",
    "Архангельск", "Чита", "Симферополь", "Калуга", "Смоленск",
    "Волжский", "Якутск", "Саранск", "Череповец", "Курган",
    "Вологда", "Орёл", "Владикавказ", "Подольск", "Грозный",
    "Мурманск", "Тамбов", "Стерлитамак", "Петрозаводск", "Кострома",
    "Нижневартовск", "Новороссийск", "Йошкар-Ола", "Таганрог",
    "Комсомольск-на-Амуре", "Сыктывкар", "Нальчик", "Шахты",
    "Дзержинск", "Орск", "Братск", "Энгельс", "Ангарск",
    "Благовещенск", "Старый Оскол", "Великий Новгород", "Королёв",
    "Химки", "Псков", "Бийск", "Прокопьевск", "Балаково", "Армавир",
    "Люберцы", "Норильск", "Петропавловск-Камчатский", "Сызрань",
    "Каменск-Уральский", "Новочеркасск", "Златоуст", "Электросталь",
    "Альметьевск", "Салават", "Миасс", "Керчь", "Копейск",
    "Пятигорск", "Майкоп", "Коломна", "Одинцово", "Хасавюрт",
    "Кисловодск", "Серпухов", "Новочебоксарск", "Нефтеюганск",
    "Домодедово", "Первоуральск", "Черкесск", "Дербент",
    "Орехово-Зуево", "Невинномысск", "Димитровград", "Кызыл",
    "Октябрьский", "Камышин", "Муром", "Новошахтинск",
    "Северодвинск", "Ногинск", "Жуковский", "Сергиев Посад",
    "Пушкино", "Артём", "Бердск", "Обнинск", "Кстово", "Рубцовск",
    "Елец", "Новокуйбышевск", "Ачинск", "Северск", "Ессентуки",
    "Магадан", "Мичуринск", "Ханты-Мансийск", "Геленджик", "Анапа",
    "Туапсе",
)

# Страны (подмножество словаря app/detectors/country.py).
_COUNTRIES = (
    "Россия", "Российская Федерация", "Беларусь", "Украина",
    "Казахстан", "Узбекистан", "Таджикистан", "Киргизия",
    "Азербайджан", "Армения", "Грузия", "Молдова", "Литва",
    "Латвия", "Эстония", "Польша", "Германия", "Франция",
    "Италия", "Испания", "Португалия", "Великобритания",
    "Соединённые Штаты Америки", "США", "Канада", "Мексика",
    "Бразилия", "Аргентина", "Чили", "Китай", "Япония", "Индия",
    "Турция", "Египет", "Израиль", "Саудовская Аравия", "ОАЭ",
    "Иран", "Ирак", "Вьетнам", "Таиланд", "Индонезия", "Малайзия",
    "Сингапур", "Австралия", "Новая Зеландия", "ЮАР", "Швейцария",
    "Швеция", "Норвегия", "Финляндия", "Дания", "Нидерланды",
    "Бельгия", "Австрия", "Чехия", "Словакия", "Венгрия", "Румыния",
    "Болгария", "Греция", "Сербия", "Хорватия", "Словения",
    "Босния и Герцеговина", "Албания", "Черногория", "Исландия",
    "Ирландия", "Люксембург", "Монако", "Андорра", "Сан-Марино",
    "Ватикан", "Мальта", "Кипр", "Монголия", "Северная Корея",
    "Южная Корея", "Куба", "Венесуэла", "Колумбия", "Перу",
    "Эквадор", "Боливия", "Парагвай", "Уругвай", "Гайана",
    "Гватемала", "Гондурас", "Никарагуа", "Коста-Рика", "Панама",
    "Доминиканская Республика", "Гаити", "Ямайка", "Бахрейн",
    "Катар", "Кувейт", "Оман", "Иордания", "Ливан", "Сирия",
    "Йемен", "Ливия", "Тунис", "Алжир", "Марокко", "Судан",
    "Эфиопия", "Танзания", "Уганда", "Гана", "Сенегал", "Камерун",
    "Ангола", "Мозамбик", "Зимбабве", "Замбия", "Ботсвана",
    "Намибия", "Мадагаскар", "Филиппины", "Бангладеш", "Шри-Ланка",
    "Непал", "Бутан", "Мьянма", "Камбоджа", "Лаос", "Бруней",
    "Восточный Тимор", "Фиджи",
)

# Улицы для адресов.
_STREETS = (
    "Тверская", "Ленина", "Советская", "Пушкина", "Гагарина",
    "Мира", "Лесная", "Центральная", "Школьная", "Садовая",
    "Набережная", "Парковая", "Заводская", "Молодёжная", "Октябрьская",
)

# Органы выдачи паспорта (для детектора issuer).
_ISSUER_ORGS = (
    "ОВД района Москвы",
    "УФМС России по г. Москве",
    "отделом УФМС по Московской области",
    "ОВД города Санкт-Петербурга",
    "отделением УФМС по Краснодарскому краю",
    "УФМС России по Новосибирской области",
    "ОВД Центрального района",
)

# Месяцы в родительном падеже (как в app/detectors/date.py).
_MONTHS = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)

# Локальные части и домены для email.
_EMAIL_LOCAL = (
    "ivan.petrov", "anna.smirnova", "sergey.kuznetsov", "olga.volkova",
    "dmitry.sokolov", "maria.ivanova", "alexey.morozov", "elena.pavlova",
)
_EMAIL_DOMAINS = ("example.com", "mail.ru", "yandex.ru", "gmail.com", "bk.ru")

# --- Независимые словари для режима --independent ---
#
# Эти словари НЕ совпадают со словарями детекторов в app/detectors/.
# Режим --independent генерирует датасет на их основе, чтобы скорер
# (tools/score.py) измерял честный F1 на данных, которых детекторы
# «не видели» при разработке, а не на замкнутом круге «генератор == детектор».

# Имена и отчества, отсутствующие в закрытом словаре app/detectors/fio.py.
_IND_NAMES = (
    "Аркадий", "Богдан", "Владислав", "Глеб", "Даниил", "Егор",
    "Захар", "Матвей", "Тимофей", "Филипп", "Эдуард", "Ярослав",
    "Алина", "Вероника", "Дарья", "Ева", "Жанна", "Зоя",
    "Карина", "Лидия", "Маргарита", "Нелли", "Полина", "Регина",
    "Снежана", "Ульяна", "Эльвира", "Юлиана",
)
_IND_PATRONYMICS = (
    "Аркадьевич", "Аркадьевна", "Богданович", "Богдановна",
    "Владиславович", "Владиславовна", "Глебович", "Глебовна",
    "Даниилович", "Данииловна", "Егорович", "Егоровна",
    "Захарович", "Захаровна", "Матвеевич", "Матвеевна",
    "Тимофеевич", "Тимофеевна", "Филиппович", "Филипповна",
    "Эдуардович", "Эдуардовна", "Ярославович", "Ярославовна",
)
# Фамилии с суффиксами, которые детектор распознаёт по морфологии,
# но с корнями, отсутствующими в генераторе по умолчанию.
_IND_SURNAMES = (
    "Абрамов", "Агафонов", "Аксёнов", "Астахов", "Балашов", "Белов",
    "Блинов", "Быков", "Власов", "Воронин", "Гаврилов", "Герасимов",
    "Гончаров", "Гусев", "Дементьев", "Дроздов", "Ефимов", "Журавлёв",
    "Зайцев", "Зуев", "Кабанов", "Киселёв", "Комаров", "Лазарев",
    "Лебедев", "Логинов", "Макеев", "Мельников", "Назаров", "Никитин",
    "Осипов", "Панфилов", "Пахомов", "Рогов", "Савельев", "Ситников",
    "Тарасов", "Тихонов", "Устинов", "Фомин", "Харитонов", "Чернов",
    "Шестаков", "Щербаков", "Юдин",
)
# Города, отсутствующие в словаре app/detectors/city.py.
_IND_CITIES = (
    "Абакан", "Азов", "Анадырь", "Апатиты", "Арзамас", "Балашов",
    "Березники", "Волгодонск", "Глазов", "Ейск", "Железногорск",
    "Зеленоград", "Ишим", "Кинешма", "Клинцы", "Лениногорск",
    "Минеральные Воды", "Новоуральск", "Озёрск", "Партизанск",
    "Ревда", "Сатка", "Тобольск", "Усть-Илимск", "Фрязино",
    "Хадыженск", "Черногорск", "Шадринск", "Щёлково", "Электроугли",
    "Южноуральск", "Ялуторовск",
)
# Страны, отсутствующие в словаре app/detectors/country.py.
_IND_COUNTRIES = (
    "Барбадос", "Белиз", "Бенин", "Буркина-Фасо", "Вануату", "Габон",
    "Гамбия", "Гвинея", "Гренада", "Джибути", "Доминика", "Кабо-Верде",
    "Коморы", "Лесото", "Либерия", "Маврикий", "Мавритания", "Малави",
    "Мали", "Нигер", "Руанда", "Свазиленд", "Сейшелы", "Сомали",
    "Того", "Тонга", "Тувалу", "Чад", "Эритрея", "Эсватини",
)
# Локальные части и домены email, отличные от используемых по умолчанию.
_IND_EMAIL_LOCAL = (
    "viktor.andreev", "nadezhda.romanova", "timofey.zhukov",
    "polina.sorokina", "arkadiy.belov", "darya.krylova",
    "matvey.volkov", "uliana.eremina",
)
_IND_EMAIL_DOMAINS = ("proton.me", "inbox.ru", "list.ru", "rambler.ru", "icloud.com")
# Улицы для адресов (не пересекаются с _STREETS).
_IND_STREETS = (
    "Абрикосовая", "Берёзовая", "Виноградная", "Горная", "Дубовая",
    "Жемчужная", "Звёздная", "Изумрудная", "Кленовая", "Луговая",
    "Морская", "Невская", "Озёрная", "Полевая", "Речная",
)
# Органы выдачи паспорта (не пересекаются с _ISSUER_ORGS).
_IND_ISSUER_ORGS = (
    "УВД по г. Твери",
    "отделом полиции г. Калуги",
    "УМВД России по Тульской области",
    "ОВД города Ярославля",
    "отделением УМВД по Рязанской области",
    "УМВД России по Вологодской области",
)

# Все типы ПД, которые генерирует датасет.
_TYPES = (
    "passport", "inn", "phone", "email", "card", "cvv", "pin", "date",
    "division_code", "license", "fio", "city", "country", "address", "issuer",
)

# Шаблоны одиночных примеров: тип -> шаблон с плейсхолдером {value}.
_SINGLE_TEMPLATES = {
    "passport": "Паспорт {value} выдан в 2020 году.",
    "inn": "ИНН налогоплательщика: {value}.",
    "phone": "Контактный телефон: {value}.",
    "email": "Электронная почта: {value}.",
    "card": "Номер карты: {value}.",
    "cvv": "CVV-код: {value}.",
    "pin": "ПИН-код: {value}.",
    "date": "Дата рождения: {value}.",
    "division_code": "Код подразделения: {value}.",
    "license": "Водительское удостоверение: {value}.",
    "fio": "Клиент: {value}.",
    "city": "Город проживания: {value}.",
    "country": "Страна: {value}.",
    "address": "Адрес: {value}.",
    "issuer": "Паспорт: {value}.",
}

# Шаблоны сложных предложений с несколькими типами.
_MULTI_TEMPLATES = (
    "Клиент {fio} проживает в городе {city}, телефон {phone}, email {email}.",
    "Паспорт {passport}, {issuer}, код подразделения {division_code}.",
    "Карта {card}, CVV {cvv}, ПИН {pin}.",
    "Дата рождения {date}, ИНН {inn}, водительское удостоверение {license}.",
    "Гражданин {country}, город {city}, адрес: {address}.",
)

# Негативные примеры (без ПД). «поэт Александр Пушкин» подавляется
# негативным контекстом детектора ФИО.
_NEGATIVE_TEMPLATES = (
    "поэт Александр Пушкин написал много стихов.",
    "адрес отделения Банка указан на сайте.",
    "Сегодня хорошая погода на улице.",
    "Курьер привезёт заказ завтра утром.",
    "Совещание перенесли на пятницу.",
    "В магазине большой выбор товаров.",
    "Проект сдали в срок.",
    "Сотрудник ушёл в отпуск на две недели.",
    "Отчёт подготовлен к концу месяца.",
    "На встрече обсудили план работ.",
)

# --- Независимые шаблоны для режима --independent ---
# Другие формулировки предложений, чтобы текст не совпадал с генератором
# по умолчанию и детекторы не «угадывали» ПД по шаблону.

_IND_SINGLE_TEMPLATES = {
    "passport": "Серия и номер паспорта: {value}.",
    "inn": "Идентификационный номер налогоплательщика {value}.",
    "phone": "Мобильный номер: {value}.",
    "email": "Почтовый ящик {value}.",
    "card": "Банковская карта {value}.",
    "cvv": "CVV-код: {value}.",
    "pin": "ПИН-код: {value}.",
    "date": "День рождения: {value}.",
    "division_code": "Код подразделения: {value}.",
    "license": "Права серии: {value}.",
    "fio": "Заявитель: {value}.",
    "city": "Место жительства: {value}.",
    "country": "Гражданство: {value}.",
    "address": "Регистрация: {value}.",
    "issuer": "Выдан: {value}.",
}

_IND_MULTI_TEMPLATES = (
    "Заявитель {fio}, проживает в {city}, связь {phone}, почта {email}.",
    "Паспорт {passport}, выдан {issuer}, код подразделения {division_code}.",
    "Карта {card}, CVV {cvv}, ПИН {pin}.",
    "Родился {date}, ИНН {inn}, водительское удостоверение {license}.",
    "Гражданин {country}, город {city}, адрес: {address}.",
)

_IND_NEGATIVE_TEMPLATES = (
    "Вчера закончили подготовку отчёта.",
    "На складе обновили остатки товара.",
    "Погода сегодня солнечная и тёплая.",
    "Документы передали в канцелярию.",
    "Собрание назначено на четверг.",
    "В отделе приняли нового сотрудника.",
    "Заявку обработали в течение дня.",
    "Планёрка перенесена на утро.",
    "Итоги подвели в конце недели.",
    "Клиентская база обновлена.",
)


# --- Вспомогательные генераторы значений ---

def _inn_check(digits: str, weights: tuple[int, ...]) -> int:
    """Контрольный разряд ИНН по весовым коэффициентам."""
    total = sum(int(d) * w for d, w in zip(digits, weights))
    return total % 11 % 10


def _luhn(digits: str) -> bool:
    """Проверка контрольной суммы Луна."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _gen_passport(rng: random.Random) -> str:
    """Серия (4 цифры, валидный регион) + номер (6 цифр)."""
    region = rng.choice(_VALID_REGIONS)
    series = f"{region:02d}{rng.randint(0, 99):02d}"
    number = f"{rng.randint(0, 999999):06d}"
    return f"{series} {number}"


def _gen_inn(rng: random.Random) -> str:
    """12 цифр с валидными контрольными разрядами."""
    base = [rng.randint(0, 9) for _ in range(10)]
    d11 = _inn_check("".join(map(str, base)), _WEIGHTS_11)
    d12 = _inn_check("".join(map(str, base)) + str(d11), _WEIGHTS_12)
    return "".join(map(str, base)) + str(d11) + str(d12)


def _gen_phone(rng: random.Random) -> str:
    """Номер телефона РФ в формате +7 XXX XXX XX XX."""
    return (
        f"+7 {rng.randint(900, 999)} {rng.randint(100, 999)} "
        f"{rng.randint(10, 99)} {rng.randint(10, 99)}"
    )


def _gen_email(rng: random.Random, local: tuple[str, ...], domains: tuple[str, ...]) -> str:
    """Email-адрес."""
    return f"{rng.choice(local)}@{rng.choice(domains)}"


def _gen_card(rng: random.Random) -> str:
    """16 цифр с валидной суммой Луна, сгруппированы по 4."""
    partial = [rng.randint(0, 9) for _ in range(15)]
    for check in range(10):
        digits = "".join(map(str, partial)) + str(check)
        if _luhn(digits):
            return f"{digits[:4]} {digits[4:8]} {digits[8:12]} {digits[12:]}"
    raise RuntimeError("не удалось сгенерировать номер карты")


def _gen_cvv(rng: random.Random) -> str:
    """3 цифры."""
    return f"{rng.randint(0, 999):03d}"


def _gen_pin(rng: random.Random) -> str:
    """4 цифры."""
    return f"{rng.randint(0, 9999):04d}"


def _gen_date(rng: random.Random) -> str:
    """Дата в числовом или текстовом формате."""
    if rng.random() < 0.5:
        month = rng.randint(1, 12)
        day = rng.randint(1, 28)
        year = rng.randint(1950, 2005)
        return f"{month:02d}.{day:02d}.{year}"
    day = rng.randint(1, 28)
    month = rng.choice(_MONTHS)
    year = rng.randint(1950, 2005)
    return f"{day} {month} {year}"


def _gen_division_code(rng: random.Random) -> str:
    """Код подразделения: 3 цифры-3 цифры."""
    return f"{rng.randint(100, 999)}-{rng.randint(100, 999)}"


def _gen_license(rng: random.Random) -> str:
    """10 цифр."""
    return f"{rng.randint(0, 9999999999):010d}"


def _gen_fio(
    rng: random.Random,
    surnames: tuple[str, ...],
    names: tuple[str, ...],
    patronymics: tuple[str, ...],
) -> str:
    """Полное ФИО: фамилия + имя + отчество."""
    return f"{rng.choice(surnames)} {rng.choice(names)} {rng.choice(patronymics)}"


def _gen_city(rng: random.Random, cities: tuple[str, ...]) -> str:
    """Название города."""
    return rng.choice(cities)


def _gen_country(rng: random.Random, countries: tuple[str, ...]) -> str:
    """Название страны."""
    return rng.choice(countries)


def _gen_address(
    rng: random.Random,
    cities: tuple[str, ...],
    streets: tuple[str, ...],
) -> str:
    """Адрес: один составной спан от первого до последнего компонента."""
    city = rng.choice(cities)
    street = rng.choice(streets)
    house = rng.randint(1, 120)
    flat = rng.randint(1, 300)
    return f"г. {city}, ул. {street}, д. {house}, кв. {flat}"


def _gen_issuer(rng: random.Random, issuer_orgs: tuple[str, ...]) -> str:
    """Орган выдачи вместе с якорным словом «выдан»."""
    return f"выдан {rng.choice(issuer_orgs)}"


# --- Конфигурация генерации: словари и шаблоны для режима по умолчанию ---

# Форматные генераторы (не зависят от словарей): passport, inn, phone,
# card, cvv, pin, date, division_code, license.
_FORMAT_GENERATORS = {
    "passport": _gen_passport,
    "inn": _gen_inn,
    "phone": _gen_phone,
    "card": _gen_card,
    "cvv": _gen_cvv,
    "pin": _gen_pin,
    "date": _gen_date,
    "division_code": _gen_division_code,
    "license": _gen_license,
}


def _default_config() -> dict:
    """Конфигурация по умолчанию: словари, согласованные с детекторами."""
    return {
        "surnames": _SURNAMES,
        "names": _NAMES,
        "patronymics": _PATRONYMICS,
        "cities": _CITIES,
        "countries": _COUNTRIES,
        "streets": _STREETS,
        "issuer_orgs": _ISSUER_ORGS,
        "email_local": _EMAIL_LOCAL,
        "email_domains": _EMAIL_DOMAINS,
        "single_templates": _SINGLE_TEMPLATES,
        "multi_templates": _MULTI_TEMPLATES,
        "negative_templates": _NEGATIVE_TEMPLATES,
    }


def _independent_config() -> dict:
    """Конфигурация независимого датасета: словари, НЕ совпадающие с детекторами.

    Используется для честной оценки скорера (tools/score.py): значения
    берутся из словарей, которых детекторы «не видели», поэтому F1 отражает
    реальную обобщающую способность, а не замкнутый круг «генератор == детектор».
    """
    return {
        "surnames": _IND_SURNAMES,
        "names": _IND_NAMES,
        "patronymics": _IND_PATRONYMICS,
        "cities": _IND_CITIES,
        "countries": _IND_COUNTRIES,
        "streets": _IND_STREETS,
        "issuer_orgs": _IND_ISSUER_ORGS,
        "email_local": _IND_EMAIL_LOCAL,
        "email_domains": _IND_EMAIL_DOMAINS,
        "single_templates": _IND_SINGLE_TEMPLATES,
        "multi_templates": _IND_MULTI_TEMPLATES,
        "negative_templates": _IND_NEGATIVE_TEMPLATES,
    }


# --- Сборка текста с фиксацией спанов в момент подстановки ---

class _Builder:
    """Собирает текст и фиксирует спаны в момент подстановки значения.

    Позиция отслеживается инкрементально при конкатенации, поэтому
    смещения не зависят от парсинга готового текста.
    """

    def __init__(self) -> None:
        self._parts: list[str] = []
        self._spans: list[dict] = []
        self._pos = 0

    def add(self, text: str) -> None:
        """Добавляет фрагмент текста без разметки."""
        self._parts.append(text)
        self._pos += len(text)

    def add_span(self, type_: str, value: str) -> None:
        """Добавляет значение и фиксирует его спан по текущей позиции."""
        start = self._pos
        self.add(value)
        self._spans.append({"type": type_, "start": start, "end": self._pos})

    def text(self) -> str:
        return "".join(self._parts)

    def spans(self) -> list[dict]:
        return self._spans


def _value_for(cfg: dict, type_: str, rng: random.Random) -> str:
    """Генерирует значение заданного типа по конфигурации cfg."""
    if type_ == "email":
        return _gen_email(rng, cfg["email_local"], cfg["email_domains"])
    if type_ == "fio":
        return _gen_fio(rng, cfg["surnames"], cfg["names"], cfg["patronymics"])
    if type_ == "city":
        return _gen_city(rng, cfg["cities"])
    if type_ == "country":
        return _gen_country(rng, cfg["countries"])
    if type_ == "address":
        return _gen_address(rng, cfg["cities"], cfg["streets"])
    if type_ == "issuer":
        return _gen_issuer(rng, cfg["issuer_orgs"])
    # Форматные типы (passport, inn, phone, card, cvv, pin, date,
    # division_code, license) не зависят от словарей.
    return _FORMAT_GENERATORS[type_](rng)


def _build_single(cfg: dict, rng: random.Random) -> dict:
    """Одиночный пример с одним типом ПД."""
    type_ = rng.choice(_TYPES)
    value = _value_for(cfg, type_, rng)
    template = cfg["single_templates"][type_]
    b = _Builder()
    prefix, suffix = template.split("{value}")
    b.add(prefix)
    b.add_span(type_, value)
    b.add(suffix)
    return {"text": b.text(), "spans": b.spans(), "negative": False}


def _build_multi(cfg: dict, rng: random.Random) -> dict:
    """Сложное предложение с несколькими типами ПД."""
    template = rng.choice(cfg["multi_templates"])
    b = _Builder()
    # Разбиваем шаблон по плейсхолдерам, подставляя значения по очереди.
    parts = template.split("{")
    b.add(parts[0])
    for part in parts[1:]:
        type_, rest = part.split("}", 1)
        value = _value_for(cfg, type_, rng)
        b.add_span(type_, value)
        b.add(rest)
    return {"text": b.text(), "spans": b.spans(), "negative": False}


def _build_negative(cfg: dict, rng: random.Random) -> dict:
    """Негативный пример без ПД."""
    b = _Builder()
    b.add(rng.choice(cfg["negative_templates"]))
    return {"text": b.text(), "spans": b.spans(), "negative": True}


def _generate(rng: random.Random, count: int, independent: bool = False) -> list[dict]:
    """Генерирует датасет: негативные, сложные и одиночные примеры.

    При independent=True используются независимые словари и шаблоны,
    не совпадающие с детекторами (для честной оценки скорера).
    """
    cfg = _independent_config() if independent else _default_config()
    n_negative = max(1, round(count * 0.10))
    n_multi = max(1, round(count * 0.25))
    n_single = max(0, count - n_negative - n_multi)

    examples: list[dict] = []
    for _ in range(n_negative):
        examples.append(_build_negative(cfg, rng))
    for _ in range(n_multi):
        examples.append(_build_multi(cfg, rng))
    for _ in range(n_single):
        examples.append(_build_single(cfg, rng))

    rng.shuffle(examples)
    return examples


def _write(path: str, examples: list[dict]) -> None:
    """Записывает датасет в JSON."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(examples, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Генератор синтетического датасета ПД")
    parser.add_argument("--out", default="tests/golden_set.json", help="путь к выходному JSON")
    parser.add_argument("--seed", type=int, default=42, help="зерно ГПСЧ")
    parser.add_argument("--count", type=int, default=200, help="число примеров")
    parser.add_argument(
        "--independent",
        action="store_true",
        help="генерировать независимый датасет (словари, не совпадающие с детекторами)",
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)
    examples = _generate(rng, args.count, independent=args.independent)
    _write(args.out, examples)
    mode = "независимый" if args.independent else "по умолчанию"
    print(f"Сгенерировано {len(examples)} примеров ({mode}) в {args.out}")


if __name__ == "__main__":
    main()