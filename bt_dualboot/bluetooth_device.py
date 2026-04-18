class BluetoothDevice:
    """Representation of bluetooth device

    Properties:
        klass (str)
        mac (str)
        name (str)
        pairing_key (str)
        adapter_mac (str)
        source (str): kind of 'Windows', 'Linux'

    """

    def __init__(
        self,
        mac=None,
        name=None,
        pairing_key=None,
        adapter_mac=None,
        device_class=None,
        source=None,
        pairing_type=None,
        pairing_data=None,
    ):
        if pairing_type is None and pairing_key is not None:
            pairing_type = self.pairing_type_link_key()

        if pairing_data is None:
            pairing_data = {}

        if pairing_key is not None and "Key" not in pairing_data:
            pairing_data["Key"] = pairing_key

        # fmt: off
        self.source         = source
        self.klass          = device_class
        self.mac            = mac
        self.name           = name
        self.pairing_key    = pairing_key
        self.adapter_mac    = adapter_mac
        self.pairing_type   = pairing_type
        self.pairing_data   = pairing_data
        # fmt: on

    def __repr__(self):
        source = "?"
        if self.source is not None:
            source = self.source[0]
        return f"{self.__class__} {source} [{self.mac}] {self.name}"

    @classmethod
    def source_linux(cls):
        return "Linux"

    @classmethod
    def source_windows(cls):
        return "Windows"

    @classmethod
    def pairing_type_link_key(cls):
        return "LinkKey"

    @classmethod
    def pairing_type_long_term_key(cls):
        return "LongTermKey"

    def is_source_linux(self):
        return self.source == "Linux"

    def is_source_windows(self):
        return self.source == "Windows"

    def is_pairing_type_long_term_key(self):
        return self.pairing_type == self.pairing_type_long_term_key()

    def pairing_fingerprint(self):
        return (
            self.pairing_type,
            tuple(sorted((key, str(value)) for key, value in self.pairing_data.items())),
        )
