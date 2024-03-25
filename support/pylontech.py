import logging
import serial
import construct
import time

log = logging.getLogger("PylonToMQTT")

class HexToByte(construct.Adapter):
    def _decode(self, obj, context, path) -> bytes:
        hexstr = ''.join([chr(x) for x in obj])
        return bytes.fromhex(hexstr)

class JoinBytes(construct.Adapter):
    def _decode(self, obj, context, path) -> bytes:
        return ''.join([chr(x) for x in obj]).encode()

class DivideBy1000(construct.Adapter):
    def _decode(self, obj, context, path) -> float:
        return obj / 1000

class DivideBy100(construct.Adapter):
    def _decode(self, obj, context, path) -> float:
        return obj / 100

#class ToVolt(construct.Adapter):
#    def _decode(self, obj, context, path) -> float:
#        return round((obj / 1000), 3)

#class ToAmp(construct.Adapter):
#    def _decode(self, obj, context, path) -> float:
#        return round((obj / 100), 2)

class ToVolt(construct.Adapter):
    def _decode(self, obj, context, path) -> float:
        return obj / 1000

class ToAmp(construct.Adapter):
    def _decode(self, obj, context, path) -> float:
        return obj / 10

class Round1(construct.Adapter):
    def _decode(self, obj, context, path) -> float:
        return round((obj), 1)

class Round2(construct.Adapter):
    def _decode(self, obj, context, path) -> float:
        return round((obj), 2)

class ToCelsius(construct.Adapter):
    def _decode(self, obj, context, path) -> float:
        return round(((obj - 2730) / 10.0), 2)  # in Kelvin*10

class Pylontech:

    module_serial_number_fmt = construct.Struct(
        "CommandValue" / construct.Byte,
        "Barcode" / construct.PaddedString(15, "utf8")
        #"ModuleSerialNumber" / JoinBytes(construct.Array(16, construct.Byte)), # Barcode was previously ModuleSerialNumber
    )

    manufacturer_info_fmt = construct.Struct(
        "DeviceName" / JoinBytes(construct.Array(10, construct.Byte)),
        #"Version" / construct.CString("utf8"),
        "Version" / construct.Array(2, construct.Byte), # MOD by Tomás Crespo: previously was "SoftwareVersion"
        "ManufacturerName" / JoinBytes(construct.GreedyRange(construct.Byte)),
    )

    get_alarm_fmt = construct.Struct(
        "NumberOfModule" / construct.Byte,
        "NumberOfCells" / construct.Int8ub,
        "CellState" / construct.Array(construct.this.NumberOfCells, construct.Int8ub),
        "NumberOfTemperatures" / construct.Int8ub,
        "CellsTemperatureStates" / construct.Array(construct.this.NumberOfTemperatures, construct.Int8ub),
        "_UserDefined1" / construct.Int8ub,
        "CurrentState" / construct.Int8ub,
        "VoltageState" / construct.Int8ub,
        "ProtectSts1" / construct.Int8ub,
        "ProtectSts2" / construct.Int8ub,
        "SystemSts" / construct.Int8ub,
        "FaultSts" / construct.Int8ub,
        "Skip81" / construct.Int16ub,
        "AlarmSts1" / construct.Int8ub,
        "AlarmSts2" / construct.Int8ub
    )

    pack_count_fmt = construct.Struct(
        "PackCount" / construct.Byte,
    )

    get_analog_fmt = construct.Struct(
        "NumberOfModule" / construct.Byte,
        "NumberOfCells" / construct.Int8ub,
        "CellVoltages" / construct.Array(construct.this.NumberOfCells, ToVolt(construct.Int16sb)),
        "NumberOfTemperatures" / construct.Int8ub,
        "GroupedCellsTemperatures" / construct.Array(construct.this.NumberOfTemperatures, ToCelsius(construct.Int16sb)),
        "Current" / ToAmp(construct.Int16sb),
        "Voltage" / ToVolt(construct.Int16ub),
        #"Power" / Round1(construct.Computed(construct.this.Current * construct.this.Voltage)),
        "Power" / construct.Computed(construct.this.Current * construct.this.Voltage),
        "_RemainingCapacity" / construct.Int16ub,
        "RemainingCapacity" / DivideBy100(construct.Computed(construct.this._RemainingCapacity)),
        "_UserDefinedItems" / construct.Int8ub,
        "TotalCapacity" / DivideBy100(construct.Int16ub),
        "CycleNumber" / construct.Int16ub,
        "TotalPower" / construct.Computed(construct.this.Power),
        "StateOfCharge" / Round1(construct.Computed(construct.this._RemainingCapacity / construct.this.TotalCapacity)),
    )


    # MOD by Tomás Crespo
    #def __init__(self, serial_port='/dev/ttyUSB0', baudrate=9600):
    #    self.s = serial.Serial(serial_port, baudrate, bytesize=8, parity=serial.PARITY_NONE, stopbits=1, timeout=5)

    # New constructor that sets the baud rate to 4800
    # @todo create the method set_baud_rate() and try to work at 115200, checking response
    def __init__(self, serial_port='/dev/ttyUSB0', baudrate=1200):
        self.s = serial.Serial(serial_port, 1200, bytesize=8, parity=serial.PARITY_NONE, stopbits=1, timeout=6)
        self.s.write(bytes([0x7E, 0x32, 0x30, 0x30, 0x31, 0x34, 0x36, 0x39, 0x31, 0x45, 0x30, 0x30, 0x32, 0x30, 0x33, 0x46, 0x44, 0x32, 0x46, 0x0D])) # Sets speed to 4800
        time.sleep(1)
        self.s.close()
        self.s = serial.Serial(serial_port, 4800, bytesize=8, parity=serial.PARITY_NONE, stopbits=1, timeout=2)
        self.s.isOpen()
        self.s.flush()    


    @staticmethod
    def get_frame_checksum(frame: bytes):
        assert isinstance(frame, bytes)
        sum = 0
        for byte in frame:
            sum += byte
        sum = ~sum
        sum %= 0x10000
        sum += 1
        return sum

    @staticmethod
    def get_info_length(info: bytes) -> int:
        lenid = len(info)
        if lenid == 0:
            return 0
        lenid_sum = (lenid & 0xf) + ((lenid >> 4) & 0xf) + ((lenid >> 8) & 0xf)
        lenid_modulo = lenid_sum % 16
        lenid_invert_plus_one = 0b1111 - lenid_modulo + 1
        return (lenid_invert_plus_one << 12) + lenid

    def send_cmd(self, address: int, cmd, info: bytes = b''):
        #print("----> Asking command {:02x} to address {:02x} with info: ".format(cmd,address), info)
        raw_frame = self._encode_cmd(address, cmd, info)
        self.s.write(raw_frame)

    def _encode_cmd(self, address: int, cid2: int, info: bytes = b''):
        cid1 = 0x46
        info_length = Pylontech.get_info_length(info)
        frame = "{:02X}{:02X}{:02X}{:02X}{:04X}".format(0x20, address, cid1, cid2, info_length).encode()
        frame += info
        frame_chksum = Pylontech.get_frame_checksum(frame)
        whole_frame = (b"~" + frame + "{:04X}".format(frame_chksum).encode() + b"\r")
        return whole_frame

    def _decode_hw_frame(self, raw_frame: bytes) -> bytes:
        # XXX construct
        frame_data = raw_frame[1:len(raw_frame) - 5]
        frame_chksum = raw_frame[len(raw_frame) - 5:-1]
        got_frame_checksum = Pylontech.get_frame_checksum(frame_data)
        assert got_frame_checksum == int(frame_chksum, 16)
        return frame_data

    def _decode_frame(self, frame):
        format = construct.Struct(
            "ver" / HexToByte(construct.Array(2, construct.Byte)),
            "adr" / HexToByte(construct.Array(2, construct.Byte)),
            "cid1" / HexToByte(construct.Array(2, construct.Byte)),
            "cid2" / HexToByte(construct.Array(2, construct.Byte)),
            "infolength" / HexToByte(construct.Array(4, construct.Byte)),
            "info" / HexToByte(construct.GreedyRange(construct.Byte)),
        )
        return format.parse(frame)

    def read_frame(self):
        raw_frame = self.s.readline()
        #print("<---- Receiving: ",raw_frame )
        f = self._decode_hw_frame(raw_frame=raw_frame)
        parsed = self._decode_frame(f)
        if (parsed.cid2 != b'\x00'):
            print(parsed)
        return parsed

    def get_pack_count(self):
        self.send_cmd(1, 0x90) # MOD by Tomás Crespo: Change ADDR from 0 to 1
        f =  self.read_frame()
        return self.pack_count_fmt.parse(f.info)

    # MOD by Tomás Crespo:
    # In RS232 protocol there is no command with code 0xC1
    # Asking for command 0xC1 returns CID2 = 0x04 = CID2 invalidation
    #def get_version_info(self, dev_id):
    #    bdevid = "{:02X}".format(dev_id).encode()
    #    self.send_cmd(0, 0xC1, bdevid) 
    #    f = self.read_frame()
    #    version_info_fmt = construct.Struct(
    #        "Version" / construct.CString("utf8")
    #    )
    #    return version_info_fmt.parse(f.info)

    # @todo query different battery id
    def get_version_info(self, dev_id):
        self.send_cmd(1, 0x51) # Command 0x51 = Get manufacturer info
        f = self.read_frame()
        return self.manufacturer_info_fmt.parse(f.info)

    # MOD by Tomás Crespo:
    # In RS232 protocol there is no command with code 0xC2
    # Asking for command 0xC1 returns CID2 = 0x04 = CID2 invalidation
    #def get_barcode(self, dev_id):
    #    bdevid = "{:02X}".format(dev_id).encode()
    #    self.send_cmd(1, 0xC2, bdevid)
    #    f = self.read_frame()
    #    version_info_fmt = construct.Struct(
    #        "Barcode" / construct.PaddedString(15, "utf8")
    #    )
    #    return version_info_fmt.parse(f.info)

    def get_barcode(self, dev_id=1): 
        if dev_id:
            bdevid = "{:02X}".format(dev_id).encode()
            self.send_cmd(1, 0x93, bdevid) # MOD by TOM: addres fixed to 1
            #self.send_cmd(dev_id, 0x93, bdevid)
        f = self.read_frame()
        # infoflag = f.info[0]
        return self.module_serial_number_fmt.parse(f.info[0:])


    def get_alarm_info(self, dev_id):
        bdevid = "{:02X}".format(dev_id).encode()
        self.send_cmd(1, 0x44, bdevid) # 0xFF all modules
        f = self.read_frame()
        il = int.from_bytes(f.infolength, byteorder='big', signed=False)
        il &= 0x0FFF
        #print("get_alarm_info infolength: {}".format(il))
        log.debug("get_alarm_info infolength: {}".format(il))
        if il > 64: # minimum response size # MOD by Tomás Crespo, changed from 22 to 64
            return self.get_alarm_fmt.parse(f.info[1:])
        else:
            return

    def get_values_single(self, dev_id):
        bdevid = "{:02X}".format(dev_id).encode()
        self.send_cmd(1, 0x42, bdevid) # MOD by Tomás Crespo, set ADDR fixed to 1 (main pack)
        f = self.read_frame()
        il = int.from_bytes(f.infolength, byteorder='big', signed=False)
        il &= 0x0FFF
        log.debug("get_values_single infolength: {}".format(il))
        if il > 45: # minimum response size 
            return self.get_analog_fmt.parse(f.info[1:])
        else:
            return


    # New methods added by Tomás Crespo
    # Gets protocol version number in VER field. V2.1 is transferred as 21H
    def get_protocol_version(self):
        self.send_cmd(1, 0x4f) 
        return self.read_frame()

    # Gets Device name, software version and manufacturer name
    def get_manufacturer_info(self):
        self.send_cmd(1, 0x51)
        f = self.read_frame()
        return self.manufacturer_info_fmt.parse(f.info)

    def get_module_serial_number(self, dev_id=1): # MOD by TOM: devid parameter from None to 1
        if dev_id:
            bdevid = "{:02X}".format(dev_id).encode()
            self.send_cmd(1, 0x93, bdevid) # MOD by TOM: addres fixed to 1
            #self.send_cmd(dev_id, 0x93, bdevid)
        #else:
            #self.send_cmd(1, 0x93) # MOD by TOM

        f = self.read_frame()
        # infoflag = f.info[0]
        return self.module_serial_number_fmt.parse(f.info[0:])

class PylonTechSOK(Pylontech):

    # SOK 48v BMS uses RS232 protocol v.2.5 (0x25)
    def _encode_cmd(self, address: int, cid2: int, info: bytes = b''):
        cid1 = 0x46
        info_length = Pylontech.get_info_length(info)
        frame = "{:02X}{:02X}{:02X}{:02X}{:04X}".format(0x25, address, cid1, cid2, info_length).encode()
        frame += info
        frame_chksum = Pylontech.get_frame_checksum(frame)
        whole_frame = (b"~" + frame + "{:04X}".format(frame_chksum).encode() + b"\r")
        return whole_frame

    # SOK 48v BMS reports 20 char version string padded with spaces (0x20)
    def get_version_info(self, dev_id):
        bdevid = "{:02X}".format(dev_id).encode()
        self.send_cmd(0, 0xC1, bdevid)
        f = self.read_frame()
        version_info_fmt = construct.Struct(
            "Version" / construct.PaddedString(20, "utf8")
        )
        return version_info_fmt.parse(f.info)
