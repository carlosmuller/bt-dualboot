import re


def hex_string_to_pairs(hex_string):
    """Convert hex string to pairs array
    Args:
        hex_string (str): kind of 'D51FFA421C4C'

    Returns:
        list: kind of [D5, 1F, FA, 42, 1C, 4C]
    """
    buf = hex_string
    buf_len = len(buf)

    if buf_len % 2 != 0:
        raise RuntimeError(f"wrong hex string={hex_string}")

    pairs_count = int(buf_len / 2)

    pairs = []
    for i in range(pairs_count):
        start = i * 2
        end = start + 2
        pairs.append(buf[start:end])

    return pairs


def is_mac_reg_key(value):
    """Check is value is valid MAC reg key
    Args:
        value (str): kind of 'd51ffa421c4c' or '"d51ffa421c4c"' or 'MasterIRK' or '"MasterIRK"'

    Returns:
        str: kind of 'D5:1F:FA:42:1C:4C'
    """

    return re.match("^[a-f0-9]{12}$", _unquote(value)) is not None


def mac_from_reg_key(mac_key):
    """Convert device MAC from Windows registry key format to regular
    Args:
        mac_key (str): kind of 'd51ffa421c4c' or '"d51ffa421c4c"'

    Returns:
        str: kind of 'D5:1F:FA:42:1C:4C'
    """

    return ":".join(hex_string_to_pairs(_unquote(mac_key).upper()))


def mac_to_reg_key(mac):
    """Convert device MAC to Windows registry key format
    Args:
        mac (str): kind of 'D5:1F:FA:42:1C:4C'

    Returns:
        str: kind of 'd51ffa421c4c'
    """

    return "".join(mac.split(":")).lower()


def hex_string_from_reg(hex_string_reg):
    """Convert hex string from Windows registry format
    Args:
        hex_string_reg (str): kind of 'hex:a6,1b,7f,1b,d9,a3,5f,3c,f7,e6,75,ef,21,61,a8,36'

    Returns:
        str: kind of 'A61B7F1BD9A35F3CF7E675EF2161A836'
    """

    _, value = hex_string_reg.split(":")
    return "".join(value.split(",")).upper()


def _reg_value_type_and_value(reg_value):
    value_type, value = reg_value.split(":", 1)
    return value_type.lower(), value


def _bytes_from_reg_value(reg_value):
    value_type, value = _reg_value_type_and_value(reg_value)

    if value_type == "dword":
        return hex_string_to_pairs(value.upper())

    if value_type in ["hex", "hex(b)"]:
        return [pair.strip().upper() for pair in value.split(",") if pair.strip() != ""]

    raise RuntimeError(f"unsupported registry value={reg_value}")


def int_from_le_reg_value(reg_value):
    """Convert little-endian Windows registry value to int.

    Supports REG_BINARY/REG_QWORD byte lists and REG_DWORD values.
    """
    value_type, value = _reg_value_type_and_value(reg_value)

    if value_type == "dword":
        return int(value, 16)

    pairs = _bytes_from_reg_value(reg_value)
    return int("".join(pairs[::-1]), 16)


def int_to_dword_reg_value(value):
    return "dword:{:08x}".format(int(value))


def int_to_qword_reg_value(value):
    pairs = hex_string_to_pairs("{:016x}".format(int(value)))
    return "hex(b):{}".format(",".join(pairs[::-1]))


def hex_string_to_reg_value(hex_string):
    """Convert hex string to Windows registry value
    Args:
        hex_string_reg (str): kind of 'A61B7F1BD9A35F3CF7E675EF2161A836'

    Returns:
        str: kind of 'hex:a6,1b,7f,1b,d9,a3,5f,3c,f7,e6,75,ef,21,61,a8,36'
    """

    value = ",".join(hex_string_to_pairs(hex_string.lower()))
    return f"hex:{value}"


def _unquote(value):
    """unquote value is quoted
    Args:
        value (str): kind of 'd51ffa421c4c' or '"d51ffa421c4c"'

    Returns:
        str: kind of 'd51ffa421c4c'
    """
    if value[0] == '"' and value[-1] == '"':
        return value[1:-1]

    return value
