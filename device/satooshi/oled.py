"""Small SSD1306 transport shared by early boot and the wallet runtime."""
REVERSE_BITS = bytes(int(f"{value:08b}"[::-1], 2) for value in range(256))


class OLED:
    def __init__(self):
        import smbus
        self.bus = smbus.SMBus(1)
        self.address = 0x3c
        for command in (0xae, 0xd5, 0x80, 0xa8, 0x3f, 0xd3, 0, 0x40,
                        0x8d, 0x14, 0x20, 0, 0xa1, 0xc8, 0xda, 0x12,
                        0x81, 0x7f, 0xd9, 0xf1, 0xdb, 0x40, 0xa4, 0xa6, 0xaf):
            self.command(command)

    def command(self, value):
        self.bus.write_byte_data(self.address, 0, value)

    def show(self, image):
        self.show_bytes(self.frame_bytes(image))

    @staticmethod
    def frame_bytes(image):
        from PIL import Image
        if image.mode != "1" or image.size != (128, 64):
            raise ValueError("Expected a 128x64 monochrome frame")
        columns = image.transpose(Image.Transpose.TRANSPOSE).tobytes()
        return bytes(REVERSE_BITS[value] for page in range(8) for value in columns[page::8])

    def show_bytes(self, data):
        if len(data) != 1024:
            raise ValueError("Expected exactly 1024 SSD1306 frame bytes")
        self.command(0x21)
        self.command(0)
        self.command(127)
        self.command(0x22)
        self.command(0)
        self.command(7)
        for start in range(0, len(data), 32):
            self.bus.write_i2c_block_data(self.address, 0x40, list(data[start:start + 32]))

    def close(self, blank=True):
        if blank:
            self.command(0xae)
        self.bus.close()
