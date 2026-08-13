import re


def convert_numbers(value):

    if value is None:
        return ""

    persian = "۰۱۲۳۴۵۶۷۸۹"
    arabic = "٠١٢٣٤٥٦٧٨٩"
    english = "0123456789"

    for p, e in zip(persian, english):
        value = value.replace(p, e)

    for a, e in zip(arabic, english):
        value = value.replace(a, e)

    return value



def is_number(value):

    value = convert_numbers(value)

    return re.fullmatch(
        r"[0-9]+",
        value
    ) is not None




def check_mobile(phone):

    phone = convert_numbers(phone)

    if not is_number(phone):
        return False

    if len(phone) != 11:
        return False

    if not phone.startswith("09"):
        return False

    return True




def check_postal(code):

    code = convert_numbers(code)

    if not is_number(code):
        return False

    return len(code) == 10




def check_national_id(code):

    code = convert_numbers(code)

    if not is_number(code):
        return False


    if len(code) != 10:
        return False


    if code == code[0] * 10:
        return False



    total = 0

    for i in range(9):

        total += int(code[i]) * (10-i)



    remainder = total % 11


    control = int(code[9])


    if remainder < 2:

        return control == remainder


    return control == 11 - remainder




def check_price(price):

    price = convert_numbers(price)

    if price == "":
        return True

    return is_number(price)
