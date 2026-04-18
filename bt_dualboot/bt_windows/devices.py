import re
from .convert import int_from_le_reg_value, mac_from_reg_key, hex_string_from_reg, is_mac_reg_key
from bt_dualboot.bluetooth_device import BluetoothDevice

REG_KEY__BLUETOOTH_PAIRING_KEYS = r"ControlSet001\Services\BTHPORT\Parameters\Keys"


def extract_adapter_mac(from_section_key):
    """Extracts adapter MAC from section key
    Args:
        from_section_key (str): kind of 'ControlSet001\\Services\\BTHPORT\\Parameters\\Keys\\d46d6d97629b'

    Returns:
        str: adapter MAC kind of 'D4:6D:6D:97:62:9B'
    """

    res = re.search("Services.BTHPORT.Parameters.Keys.([a-f0-9]+)$", from_section_key)
    if res is None:
        return None

    return mac_from_reg_key(res.groups()[0])


def extract_adapter_and_device_mac(from_section_key):
    """Extracts adapter and BLE device MACs from a Windows registry section key."""

    res = re.search("Services.BTHPORT.Parameters.Keys.([a-f0-9]+).([a-f0-9]+)$", from_section_key)
    if res is None:
        return None

    adapter_mac, device_mac = res.groups()
    return {
        "adapter_mac": mac_from_reg_key(adapter_mac),
        "device_mac": mac_from_reg_key(device_mac),
    }


def _unquote(value):
    if value[0] == '"' and value[-1] == '"':
        return value[1:-1]

    return value


def _section_dict(section):
    return {_unquote(key).lower(): value for key, value in section.items()}


def get_devices(windows_registry):
    """Returns all BluetoothDevice instances from windows registry
    Args:
        windows_registry (WindowsRegistry): instance used for export data

    Returns:
        list<BluetoothDevice>
            NOTE: filled only `mac`, `adapter_mac` and `pairing_key`
    """

    reg_data = windows_registry.export_as_config(REG_KEY__BLUETOOTH_PAIRING_KEYS)

    bluetooth_devices = []
    for section_key in reg_data.keys():
        adapter_mac = extract_adapter_mac(section_key)
        if adapter_mac is None:
            macs = extract_adapter_and_device_mac(section_key)
            if macs is None:
                continue

            section = _section_dict(reg_data[section_key])
            if "ltk" not in section:
                continue

            pairing_data = {
                "Key": hex_string_from_reg(section["ltk"]),
                "EncSize": str(int_from_le_reg_value(section.get("keylength", "dword:00000010"))),
                "EDiv": str(int_from_le_reg_value(section.get("ediv", "dword:00000000"))),
                "Rand": str(
                    int_from_le_reg_value(
                        section.get("erand", "hex(b):00,00,00,00,00,00,00,00")
                    )
                ),
            }
            optional_key_map = {
                "IRK": "irk",
                "CSRK": "csrk",
                "CSRKInbound": "csrkinbound",
            }
            for data_key, registry_key in optional_key_map.items():
                if registry_key in section:
                    pairing_data[data_key] = hex_string_from_reg(section[registry_key])

            bluetooth_devices.append(
                BluetoothDevice(
                    source=BluetoothDevice.source_windows(),
                    mac=macs["device_mac"],
                    adapter_mac=macs["adapter_mac"],
                    pairing_key=pairing_data["Key"],
                    pairing_type=BluetoothDevice.pairing_type_long_term_key(),
                    pairing_data=pairing_data,
                )
            )
            continue

        section = reg_data[section_key]
        for device_mac_raw, pairing_key_raw in section.items():
            if not is_mac_reg_key(device_mac_raw):
                continue

            bluetooth_devices.append(
                BluetoothDevice(
                    source=BluetoothDevice.source_windows(),
                    mac=mac_from_reg_key(device_mac_raw),
                    adapter_mac=adapter_mac,
                    pairing_key=hex_string_from_reg(pairing_key_raw),
                )
            )

    return bluetooth_devices
