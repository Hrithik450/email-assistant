import re

EMAIL_PATTERN = re.compile(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w.-]+\.[A-Za-z]{2,}")


def clean_value(value):
    return str(value or "").strip().strip("\"'").strip()


def parseaddr(address):
    address = clean_value(address)
    if not address:
        return "", ""

    angle_match = re.search(r"^(.*?)<([^<>]+)>", address)
    if angle_match:
        name = clean_value(angle_match.group(1))
        email = clean_value(angle_match.group(2))
        return name, email

    email_match = EMAIL_PATTERN.search(address)
    if email_match:
        return "", email_match.group(0)

    return "", address


def split_addresses(addresses):
    "Splits a string of email addresses separated by commas, but ignores commas that are inside quoted names or inside angle brackets"

    parts = []
    current = []
    in_quotes = False
    angle_depth = 0

    for char in addresses:
        if char == '"':
            in_quotes = not in_quotes
        elif char == "<" and not in_quotes:
            angle_depth += 1
        elif char == ">" and not in_quotes and angle_depth:
            angle_depth -= 1

        if char == "," and not in_quotes and angle_depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)

    if current:
        parts.append("".join(current).strip())

    return [part for part in parts if part]


def getaddresses(fieldvalues):
    parsed_addresses = []

    for fieldvalue in fieldvalues:
        for address in split_addresses(str(fieldvalue or "")):
            parsed_addresses.append(parseaddr(address))

    return parsed_addresses
