# mpy-img-decoder
PNG and JPEG decoder / parser / renderer in pure micropython. Decodes PNG and JPEG files/byte buffers and outputs pixel colors  
### Why pure micropython and not C module?
Some board firmware forks are not open source and it's not possible to add extra C modules in them  

## PNG decoder
Written from scratch, highly optimized, supports all bit/color modes, supports all main PNG chunks, 1 background-color based transparency, multi-part IDAT chunks, does not support Adam7 interlacing.

## JPG decoder
Ported from python2 [enmasse/jpeg_read](https://github.com/enmasse/jpeg_read) and optimized a little bit to work on 80kb of free RAM. It's still much slower than PNG decoder and requires much more RAM to decode. Image dimensions affect the amount of required RAM.

# Usage
```python
from PNGdecoder import png 
from JPEGdecoder import jpeg
png('image.png', callback=lcd.drawPixel).render(0, 0)
jpeg('image.jpg', callback=lcd.drawPixel).render(32, 32)
```

### png / jpeg function parameters
###### required  
**source** - file path or bytes object of the source image  
**callback** - function, that will be called to output every pixel color at coordinates x and y `callback(x, y, color)`  
###### optional  
**cache** - bool, if true, stores decoder output in RAM cache to re-render the image quickly  
**quality** - [JPEG ONLY] int (1-8), output image quality, affects processing speed  
**fastalpha** - [PNG ONLY] bool, if True, only detects 100% transparent colors to not render them  
**bg** - [PNG ONLY] (R, G, B) tuple with values from 0 to 255 with background color for PNG transparency calculation when fastalpha is False  

png/jpeg function works as a constructor and returns a ~Renderer class isntance

### ~Renderer class
**file** - input file, from source argument  
**getMeta()** - function, returns width, height, bit depth (and color mode, only for PNG)  
**render(x,y [,placeholder, phcolor])** - function, starts decoding and rendering process. JPG renderer can be called only once per instance, if caching is not used, due to memory-optimized rendering process. PNG renderer can be used multiple times. x, y - offset coordinates. placeholder - function that draws something before decoding process, `placeholder(x, y, width, height, color)`, phcolor - color that will be used in placeholder function call. Returns same renderer class instance.  
**checkAndRender(w, h, wxh)** - function, checks if width and height of the image or their product are less than specified ones, then renders the image, supports all parameters for render function  

