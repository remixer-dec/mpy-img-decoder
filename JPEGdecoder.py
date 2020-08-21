#"""
#    jpeg decoder. Copyright (C) 2010 Mats Alritzson
#    ported from Python2 to micropython by Remixer Dec
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#"""
from array import array
from math import *
from io import BytesIO
import gc


def jpeg(source, quality=8, callback=print, cache=False):
    if quality < 1 or quality > 8:
        raise ValueError('Quality must be between 1 and 8')
    huffman_ac_tables = [{}, {}, {}, {}]
    huffman_dc_tables = [{}, {}, {}, {}]

    q_table = [[], [], [], []]

    XYP = 0, 0, 0
    bit_stream = 0
    component = {}
    num_components = 0
    mcus_read = 0
    inline_dc = 0
    rx = 0
    ry = 0

    idct_precision = quality

    EOI = False
    cached = array('i')
    cachedX = array('B')
    cachedY = array('B')
    data = []
    pint = int

    offsety = 0
    offsetx = 0

    idct_table = 0
    range8 = range(8)
    rangeIDCT = range(idct_precision)

    @micropython.viper
    def rgb_to_int(RGBlist) -> int:
        return (int(RGBlist[0]) << 0x10) + (int(RGBlist[1]) << 0x8) + int(
            RGBlist[2])

    @micropython.viper
    def bint(inp) -> int:
        return int(pint.from_bytes(inp, 'little'))

    @micropython.viper
    def intb(inp):
        return bytes([inp])

    @micropython.viper
    def read_word(file) -> int:
        out = int(bint(file.read(1))) << 8
        out |= int(bint(file.read(1)))
        return out

    @micropython.viper
    def read_byte(file):
        out = bint(file.read(1))
        return out

    @micropython.viper
    def map_codes_to_values(codes, values):
        out = {}
        for i in range(int(len(codes))):
            out[codes[i]] = values[i]
        return out

    @micropython.viper
    def read_dht(file):
        nonlocal huffman_ac_tables
        nonlocal huffman_dc_tables

        Lh = int(read_word(file))
        Lh -= 2
        while Lh > 0:
            huffsize = []
            huffval = []
            T = int(read_byte(file))
            Th = T & 0x0F
            Tc = (T >> 4) & 0x0F
            Lh = Lh - 1

            for i in range(16):
                huffsize.append(read_byte(file))
                Lh -= 1

            huffcode = huffman_codes(huffsize)
            for j in huffcode:
                huffval.append(read_byte(file))
                Lh -= 1

            if Tc == 0:
                huffman_dc_tables[Th] = map_codes_to_values(huffcode, huffval)
            else:
                huffman_ac_tables[Th] = map_codes_to_values(huffcode, huffval)

    @micropython.viper
    def huffman_codes(huffsize):
        huffcode = []
        code = 0

        for i in range(int(len(huffsize))):
            si = int(huffsize[i])
            for k in range(si):
                huffcode.append((i + 1, code))
                code += 1

            code <<= 1

        return huffcode

    @micropython.viper
    def read_dqt(file):
        nonlocal q_table

        Lq = int(read_word(file))
        Lq -= 2
        while Lq > 0:
            table = []
            Tq = int(read_byte(file))
            Pq = Tq >> 4
            Tq &= 0xF
            Lq -= 1

            if Pq == 0:
                for i in range(64):
                    table.append(int(read_byte(file)))
                    Lq -= 1

            else:
                for i in range(64):
                    val = read_word(file)
                    table.append(val)
                    Lq -= 2

            q_table[Tq] = table

    @micropython.native
    def read_sof(type, file):
        nonlocal component
        nonlocal XYP

        Lf = read_word(file)
        Lf -= 2
        P = read_byte(file)
        Lf -= 1
        Y = read_word(file)
        Lf -= 2
        X = read_word(file)
        Lf -= 2
        Nf = read_byte(file)
        Lf -= 1

        XYP = X, Y, P

        while Lf > 0:
            C = read_byte(file)
            V = read_byte(file)
            Tq = read_byte(file)
            Lf -= 3
            H = V >> 4
            V &= 0xF
            component[C] = {}
            component[C]['H'] = H
            component[C]['V'] = V
            component[C]['Tq'] = Tq

    @micropython.viper
    def read_app(type, file):
        Lp = int(read_word(file))
        Lp -= 2
        file.seek(Lp, 1)

    @micropython.native
    def read_dnl(file):
        nonlocal XYP

        Ld = read_word(file)
        Ld -= 2
        NL = read_word(file)
        Ld -= 2

        X, Y, P = XYP

        if Y == 0:
            XYP = X, NL, P

    @micropython.native
    def read_sos(file):
        nonlocal component
        nonlocal num_components

        Ls = int(read_word(file))
        Ls -= 2

        Ns = int(read_byte(file))
        Ls -= 1

        for i in range(Ns):
            Cs = int(read_byte(file))
            Ls -= 1
            Ta = int(read_byte(file))
            Ls -= 1
            Td = Ta >> 4
            Ta &= 0xF
            component[Cs]['Td'] = Td
            component[Cs]['Ta'] = Ta

        Ss = read_byte(file)
        Ls -= 1
        Se = read_byte(file)
        Ls -= 1
        A = read_byte(file)
        Ls -= 1

        num_components = Ns

    @micropython.viper
    def calc_add_bits(len: int, val: int) -> int:
        if (val & (1 << len - 1)):
            pass
        else:
            val -= (1 << len) - 1

        return val

    @micropython.native
    def bit_read(file):
        nonlocal EOI
        nonlocal inline_dc

        input = file.read(1)
        while input and not EOI:
            if input == intb(0xFF):
                cmd = file.read(1)
                if cmd:
                    if cmd == intb(0x00):
                        input = intb(0xFF)
                    elif cmd == intb(0xD9):
                        EOI = True
                    elif 0xD0 <= bint(cmd) <= 0xD7 and inline_dc:
                        input = file.read(1)
                    else:
                        input = file.read(1)
            if not EOI:
                for i in range(7, -1, -1):
                    yield (ord(input) >> i) & 0x01
                input = file.read(1)

        while True:
            yield -1

    @micropython.viper
    def get_bits(num: int, gen) -> int:
        out = 0
        for i in range(num):
            out <<= 1
            val = int(next(gen))
            if val != -1:
                out += val & 0x01
            else:
                return -1
        return out

    @micropython.viper
    def read_data_unit(comp_num: int):
        nonlocal bit_stream
        nonlocal component

        #gc.collect()
        data = array('h')

        comp = component[comp_num]
        huff_tbl = huffman_dc_tables[comp['Td']]

        while int(len(data)) < 64:
            key = 0

            for bits in range(1, 17):
                key_len = -1
                key <<= 1

                val = int(get_bits(1, bit_stream))
                if val == -1:
                    break
                key |= val

                if (bits, key) in huff_tbl:
                    key_len = int(huff_tbl[(bits, key)])
                    break

            huff_tbl = huffman_ac_tables[comp['Ta']]

            if key_len == -1:
                break

            elif key_len == 0xF0:
                for i in range(16):
                    data.append(0)
                continue

            if int(len(data)) != 0:
                if key_len == 0x00:
                    while int(len(data)) < 64:
                        data.append(0)
                    break

                for i in range(key_len >> 4):
                    if int(len(data)) < 64:
                        data.append(0)
                key_len &= 0x0F

            if int(len(data)) >= 64:
                break

            if key_len != 0:
                val = int(get_bits(key_len, bit_stream))
                if val == -1:
                    break
                num = int(calc_add_bits(key_len, val))

                data.append(num)
            else:
                data.append(0)

        return data

    @micropython.native
    def restore_dc(data):
        dc_prev = array('h', [0 for x in range(len(data[0]))])
        out = []

        for mcu in data:
            for comp_num in range(len(mcu)):
                for du in range(len(mcu[comp_num])):
                    if mcu[comp_num][du]:
                        mcu[comp_num][du][0] += dc_prev[comp_num]
                        dc_prev[comp_num] = mcu[comp_num][du][0]

            out.append(mcu)
        return out

    @micropython.native
    def read_mcu():
        nonlocal component
        nonlocal num_components
        nonlocal mcus_read

        comp_num = mcu = list(range(num_components))

        for i in comp_num:
            comp = component[i + 1]
            mcu[i] = []
            for j in range(comp['H'] * comp['V']):
                if not EOI:
                    mcu[i].append(read_data_unit(i + 1))

        mcus_read += 1
        return mcu

    @micropython.viper
    def dequantify(mcu):
        nonlocal component
        gc.collect()

        out = mcu
        for c in range(int(len(out))):
            for du in range(int(len(out[c]))):
                for i in range(int(len(out[c][du]))):
                    out[c][du][i] = int(out[c][du][i]) * int(
                        q_table[component[c + 1]['Tq']][i])

        return out

    @micropython.viper
    def zagzig(du):
        map = [
            array('h', [0, 1, 5, 6, 14, 15, 27, 28]),
            array('h', [2, 4, 7, 13, 16, 26, 29, 42]),
            array('h', [3, 8, 12, 17, 25, 30, 41, 43]),
            array('h', [9, 11, 18, 24, 31, 40, 44, 53]),
            array('h', [10, 19, 23, 32, 39, 45, 52, 54]),
            array('h', [20, 22, 33, 38, 46, 51, 55, 60]),
            array('h', [21, 34, 37, 47, 50, 56, 59, 61]),
            array('h', [35, 36, 48, 49, 57, 58, 62, 63])
        ]
        ldu = int(len(du))

        for x in range(8):
            for y in range(8):
                if int(map[x][y]) < ldu:
                    map[x][y] = int(du[map[x][y]])
                else:
                    map[x][y] = 0
            #gc.collect()
        return map

    @micropython.viper
    def for_each_du_in_mcu(mcu, func):
        gc.collect()
        for i, comp in enumerate(mcu):
            for ii, cm in enumerate(mcu[i]):
                mcu[i][ii] = func(cm)

        return mcu

    @micropython.viper
    def C(x: int):
        if x == 0:
            return 1.0 / sqrt(2.0)
        else:
            return 1.0

    @micropython.viper
    def idct(matrix):
        out = [array('b', range(8)) for i in range(8)]
        for x in range8:
            for y in range8:
                sum = 0
                for u in rangeIDCT:
                    for v in rangeIDCT:
                        sum += int(
                            round(matrix[v][u] * idct_table[u][x] * idct_table[v][y]))

                out[y][x] = int(sum // 4)

        return out

    @micropython.viper
    def show_all(data):
        H = array('b')
        V = array('b')

        for i in range(int(num_components)):
            H.append(component[i + 1]['H'])
            V.append(component[i + 1]['V'])

        for mcu in data:
            show(mcu, H, V)

    @micropython.native
    def setOffsetX(val, bx=False, by=False):
        nonlocal offsetx
        if cache and bx and by:
            cachedX.append(bx)
            cachedY.append(by)
        offsetx = val

    @micropython.native
    def setOffsetY(val):
        nonlocal offsety
        offsety = val

    @micropython.native
    def prepareArr(ho, vo):
        return [[array('b') for x in range(8 * int(ho))] for y in range(8 * int(vo))]

    def showCached():
        nonlocal offsetx, offsety
        X, Y, P = XYP
        ind = 0
        offsetx = 0
        offsety = 0
        for i in range(len(cachedX)):
            bX = cachedX[i]
            bY = cachedY[i]
            for y in range(bY):
                for x in range(bX):
                    callback(rx + x + offsetx, ry + y + offsety, cached[ind])
                    ind += 1
            offsetx += bX
            if offsetx > X:
                offsetx = 0
                offsety += bY

    @micropython.viper
    def show(mcu, H, V):
        #print(gc.mem_free())
        Hout = int(max(H))
        Vout = int(max(V))

        #gc.collect()

        out = prepareArr(Hout, Vout)
        for i in range(int(len(mcu))):
            Hs = int(Hout // int(H[i]))
            Vs = int(Vout // int(V[i]))
            Hin = int(H[i])
            Vin = int(V[i])
            comp = mcu[i]

            if int(len(comp)) != int(Hin * Vin):
                return []

            for v in range(Vout):
                for h in range(Hout):
                    a = int((h // Hs) + Hin * (v // Vs))
                    for y in range(8):
                        b = int(y // Vs)
                        for x in range(8):
                            c = int(x // Hs)
                            out[y + v * 8][x + h * 8].append(comp[a][b][c])
                        #gc.collect()
        mcu.clear()
        X, Y, P = XYP
        ybmax = int(min(Y, len(out)))
        for y in range(ybmax):
            xbmax = int(min(X, len(out[y])))
            if y + int(offsety) > int(Y):
                break
            for x in range(xbmax):
                if x + int(offsetx) > int(X):
                    break
                clr = out[y][x]
                rgbClr = int(rgb_to_int(YCbCr2RGB(clr[0], clr[1], clr[2])))
                callback(
                    int(rx) + x + int(offsetx),
                    int(ry) + y + int(offsety), rgbClr)
                if cache:
                    cached.append(rgbClr)

        setOffsetX(int(offsetx) + xbmax, xbmax, ybmax)
        if offsetx >= X:
            setOffsetX(0)
            setOffsetY(int(offsety) + ybmax)
        out.clear()
        return []

    @micropython.viper
    def clip(x: int) -> int:
        if x > 255:
            return 255
        elif x < 0:
            return 0
        else:
            return int(x)

    @micropython.viper
    def clamp(x: int) -> int:
        x = int((int(abs(x)) + x) // 2)
        if int(x) > 255:
            return 255
        else:
            return int(round(x))

    @micropython.viper
    def YCbCr2RGB(Y, Cb, Cr):
        Cred = 0.299
        Cgreen = 0.587
        Cblue = 0.114

        R = Cr * (2. - 2. * Cred) + Y
        B = Cb * (2. - 2. * Cblue) + Y
        G = (Y - Cblue * B - Cred * R) / Cgreen

        return clamp(round(R + 128.)), clamp(round(G + 128.)), clamp(round(B + 128.))

    @micropython.viper
    def YCbCr2Y(Y, Cb, Cr):
        return Y, Y, Y

    def processFile(filename, onlyMeta=False):
        nonlocal bit_stream, idct_table, data, huffman_ac_tables, huffman_dc_tables, idct_table, q_table
        idct_table = [ array('f', [(C(u) * cos(((2.0 * x + 1.0) * u * pi) / 16.0)) for x in range(8)]) for u in range(idct_precision)]

        if isinstance(filename, str):
            input_file = open(filename, "rb")
        elif isinstance(filename, bytes):
            input_file = BytesIO(filename)

        in_char = input_file.read(1)

        while in_char:
            if in_char == intb(0xff):
                in_char = input_file.read(1)
                in_num = bint(in_char)
                if 0xe0 <= in_num <= 0xef:
                    read_app(in_num - 0xe0, input_file)
                elif in_num == 0xdb:
                    read_dqt(input_file)
                elif in_num == 0xdc:
                    read_dnl(input_file)
                elif in_num == 0xc4:
                    read_dht(input_file)
                elif 0xc0 <= in_num <= 0xcf:
                    read_sof(in_num - 0xc0, input_file)
                    if onlyMeta:
                        return XYP
                elif in_num == 0xda:
                    read_sos(input_file)
                    bit_stream = bit_read(input_file)
                    while not EOI:
                        data.append(read_mcu())

            in_char = input_file.read(1)
        input_file.close()
        if not inline_dc:
            data = restore_dc(data)

        #print("dequantify")
        data = map(dequantify, data)
        del huffman_ac_tables
        del huffman_dc_tables

        #print("deserialize")
        data = [for_each_du_in_mcu(mcu, zagzig) for mcu in data]

        #print("inverse discrete cosine transform")
        data = [for_each_du_in_mcu(mcu, idct) for mcu in data]
        del idct_table
        del q_table
        gc.collect()

        #print("combine mcu")
        data = show_all(data)
        del data
        del input_file

    class JPEGRenderer():
        def __init__(self):
            self.file = source
            self.wasRendered = False

        def getMeta(self):
            return processFile(self.file, True)

        def checkAndRender(self, w=False, h=False, wxh=False, **kwargs):
            X, Y, P = self.getMeta()
            if w and X > w:
                return
            if h and Y > h:
                return
            if wxh and X * Y > wxh:
                return
            self.render(**kwargs)

        @micropython.native
        def render(self, x=0, y=0, placeholder=False, phcolor=0xBBBBBB):
            nonlocal rx, ry
            rx = x
            ry = y
            if not self.wasRendered:
                if placeholder:
                    W, H, P = self.getMeta()
                    placeholder(x, y, W, H, phcolor)
                processFile(self.file)
                self.wasRendered = True
            else:
                if cached:
                    showCached()
                else:
                    raise Exception('already rendered!')
            return self

    return JPEGRenderer()
