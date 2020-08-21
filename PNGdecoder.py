# PNG decoder. Copyright (C) 2020 Remixer Dec
# License: GNU General Public License version 3 -> http://www.gnu.org/licenses/

import zlib
from array import array
from io import BytesIO


def png(source, callback=print, cache=False, bg=(0, 0, 0), fastalpha=True):
    chunkSize = 0
    chunkType = 0
    bpp = 4
    channels = [1, 0, 3, 1, 2, 0, 4]
    palette = []
    WHDC = False
    INT = int
    rx = 0
    ry = 0
    end = False
    cached = array('i')
    empty = array('b', [-1, -1, -1])

    @micropython.viper
    def rgb2int(RGBlist) -> int:
        return (int(RGBlist[0]) << 0x10) + (int(RGBlist[1]) << 0x8) + int(RGBlist[2])

    @micropython.viper
    def parsePNG(src, onlymeta=False):
        nonlocal end
        if isinstance(src, str):
            src = open(src, "rb")
        elif isinstance(src, bytes):
            src = BytesIO(src)
        header = src.read(8)
        if header != b'\x89\x50\x4e\x47\x0d\x0a\x1a\x0a':
            return
        while not end:
            readChunkMeta(src)
            readChunk(src)
            if onlymeta:
                return WHDC
            src.seek(4, 1)
        src.close()

    @micropython.native
    def readChunkMeta(src):
        nonlocal chunkSize, chunkType
        chunkSize = bint(src.read(4))
        chunkType = src.read(4)

    @micropython.viper
    def bint(inp) -> int:
        return int(INT.from_bytes(inp, 'big'))

    @micropython.native
    def truediv(a, b):
        return a / b

    @micropython.viper
    def rgba2rgb(r: int, g: int, b: int, a: int):
        if fastalpha:
            return [r, g, b] if a != 0 else empty
        if a == 0:
            return empty
        fr = float(r)
        fg = float(g)
        fb = float(b)
        fa = float(truediv(a, 255))
        R = round(fr * fa)
        G = round(fg * fa)
        B = round(fb * fa)
        return R, G, B

    @micropython.viper
    def readChunk(src):
        supported = {
            b'IHDR': readIHDR,
            b'PLTE': readPLTE,
            b'IDAT': readIDAT,
            b'IEND': readIEND
        }
        if chunkType in supported:
            supported[chunkType](src)
        else:
            src.seek(chunkSize, 1)

    def readIEND(src):
        nonlocal end
        end = True
        return

    @micropython.native
    def readIHDR(src):
        nonlocal WHDC
        WHDC = tuple(map(bint, (src.read(4), src.read(4), src.read(1), src.read(1))))
        src.seek(3, 1)

    @micropython.native
    def readPLTE(src):
        nonlocal palette
        for i in range(round(chunkSize // 3)):
            palette.append(src.read(3))

    @micropython.native
    def getRealBpp(c, d, w):
        rbpp = c * d / 8
        bp = round(rbpp)
        br = round(rbpp * w)
        return (br, bp)

    @micropython.viper
    def getSlicedItem(item, start, end):
        return item[start:end]

    @micropython.native
    def setBpp(value):
        nonlocal bpp
        bpp = value
        return bpp

    @micropython.native
    def setChunkSize(value):
        nonlocal chunkSize
        chunkSize = value
        return chunkSize

    @micropython.viper
    def show(x, y, c: int):
        if cache:
            cached.append(c)
        if c > 0:
            callback(x, y, c)

    @micropython.viper
    def readIDAT(src):
        isNextChunkIDAT = True
        fullchunk = b''
        while isNextChunkIDAT:
            fullchunk += src.read(chunkSize)
            src.seek(4, 1)
            nextSize = bint(src.read(4))
            isNextChunkIDAT = bool(src.read(4) == b'IDAT')
            if not isNextChunkIDAT:
                src.seek(12 * -1, 1)
            setChunkSize(nextSize)  #chunkSize = nextSize
        idat = zlib.decompress(fullchunk)
        idat = BytesIO(idat)
        W = int(WHDC[0])
        H = int(WHDC[1])
        D = int(WHDC[2])
        C = int(WHDC[3])
        bToRead, obpp = getRealBpp(channels[C], D, W)
        bpp = int(setBpp(obpp))  #bpp = int(obpp)
        prevrow = b''
        andbits = ((1 << D) - 1)
        for y in range(H):
            ftype = bint(idat.read(1))
            row = idat.read(int(bToRead))
            row = applyFilter(ftype, row, y, prevrow)
            for x in range(W):
                if D >= 8:
                    clr = rgb2int(
                        readColor(
                            getSlicedItem(row,
                                          int(x) * int(bpp),
                                          int(x) * int(bpp) + int(bpp)), D, C))
                else:
                    bpb = int(8 // D)
                    realx = (x // bpb +
                             1 * int(x % bpb != 0)) - 1 * int(x != 0)
                    clrB = getSlicedItem(row, realx, realx + 1)
                    idx = int(x == 0) + x % bpb or bpb
                    clrI = int(clrB[0]) >> (8 - D * idx) & andbits
                    #gets needed bits from a byte^
                    clr = rgb2int(readColor(clrI, D, C))
                show(int(rx) + x, int(ry) + y, clr)
            prevrow = row

    @micropython.viper
    def readColor(src, depth: int, colormode: int):
        if colormode == 3:
            if not isinstance(src, INT):
                x = int(src[0])
            else:
                x = int(src)
            r, g, b = palette[x]
            return (r, g, b)
        if colormode == 0:
            if depth <= 4:
                maxClr = (1 << depth) - 1
                clr = round(int(src) * 255 // maxClr)
                return (clr, clr, clr)
            if depth == 8:
                gs = src
                return (gs, gs, gs)
            if depth == 16:
                gs, a = src
                return rgba2rgb(gs, gs, gs, a)
        if colormode == 4:
            if depth == 8:
                gs, a = src
            if depth == 16:
                gs, gs2, a, a2 = src
            return rgba2rgb(gs, gs, gs, a)
        if colormode == 2:
            if depth == 8:
                r, g, b = src
            if depth == 16:
                r, r2, g, g2, b, b2 = src
            return (r, g, b)
        if colormode == 6:
            if depth == 8:
                r, g, b, a = src
            if depth == 16:
                r, r2, g, g2, b, b2, a, a2 = src
            return rgba2rgb(r, g, b, a)

    @micropython.native
    def applyFilter(f, row, y, prevrow):
        @micropython.viper
        def PaethPredictor(a: int, b: int, c: int) -> int:
            p = a + b - c
            pa = abs(p - a)
            pb = abs(p - b)
            pc = abs(p - c)
            if pa <= pb and pa <= pc:
                Pr = a
            elif pb <= pc:
                Pr = b
            else:
                Pr = c
            return Pr

        @micropython.native
        def ReconA(c: int) -> int:
            return out[c - int(bpp)] if c >= int(bpp) else 0

        @micropython.native
        def ReconB(r: int, c: int) -> int:
            return prevrow[c] if r > 0 else 0

        @micropython.native
        def ReconC(r: int, c: int) -> int:
            return prevrow[c - int(bpp)] if r > 0 and c >= int(bpp) else 0

        @micropython.viper
        def f0(x, r, c):
            return x

        @micropython.viper
        def f1(x, r, c) -> int:
            return int(x + ReconA(c))

        @micropython.viper
        def f2(x, r, c) -> int:
            return int(x + ReconB(r, c))

        @micropython.viper
        def f3(x: int, r, c) -> int:
            return int(x + int(ReconA(c) + ReconB(r, c)) // 2)

        @micropython.viper
        def f4(x: int, r, c) -> int:
            return x + int(PaethPredictor(ReconA(c), ReconB(r, c), ReconC(r, c)))

        ftypes = [f0, f1, f2, f3, f4]
        out = array('B')
        if f >= 0 and f < 5:
            for i in range(len(row)):
                out.append(ftypes[f](row[i], y, i) & 0xFF)
        return out

    @micropython.native
    def showCached():
        i = 0
        W, H, D, C = WHDC
        for y in range(H):
            for x in range(W):
                if cached[i] > 0:
                    callback(rx + x, ry + y, cached[i])
                i += 1

    class PNGRenderer():
        def __init__(self):
            self.file = source

        def getMeta(self):
            return WHDC or parsePNG(self.file, True)

        def checkAndRender(self, w=False, h=False, wxh=False, **kwargs):
            W, H, D, C = self.getMeta()
            if w and W > w:
                return
            if h and H > h:
                return
            if wxh and W * H > wxh:
                return
            self.render(**kwargs)

        @micropython.native
        def render(self, x=0, y=0, placeholder=False, phcolor=0xBBBBBB):
            nonlocal rx, ry, end, palette
            rx = x
            ry = y
            if not cached:
                palette = []
                end = False
                if placeholder:
                    W, H, D, C = self.getMeta()
                    placeholder(x, y, W, H, phcolor)
                parsePNG(self.file, False)
            else:
                showCached()
            return self

    return PNGRenderer()
