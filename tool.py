
from PIL import Image, ImageOps
import exifread
import os

def thumbnail_image(input_file, output_file, max_size=(1000, 1000), resample=3, ext='webp'):
    im = Image.open(input_file)
    im.thumbnail(max_size, resample=resample)
    im = ImageOps.exif_transpose(im)
    im.save(output_file, format=ext, optimize=True)

# barrowed from 
# https://gist.github.com/snakeye/fdc372dbf11370fe29eb 
def _convert_to_degress(value):
    """
    Helper function to convert the GPS coordinates stored in the EXIF to degress in float format
    :param value:
    :type value: exifread.utils.Ratio
    :rtype: float
    """
    d = float(value.values[0].num) / float(value.values[0].den)
    m = float(value.values[1].num) / float(value.values[1].den)
    s = float(value.values[2].num) / float(value.values[2].den)

    return d + (m / 60.0) + (s / 3600.0)

def read_gps(file_name: str):
    if not os.path.exists(file_name):
        return []
    
    with open(file_name, 'rb') as f:
        exif_dict = exifread.process_file(f)
        latitude = exif_dict.get('GPS GPSLatitude')
        latitude_ref = exif_dict.get('GPS GPSLatitudeRef')
        longitude = exif_dict.get('GPS GPSLongitude')
        longitude_ref = exif_dict.get('GPS GPSLongitudeRef')
        if latitude:
            lat_value = _convert_to_degress(latitude)
            if latitude_ref.values != 'N':
                lat_value = -lat_value
        else:
            return []
        if longitude:
            lon_value = _convert_to_degress(longitude)
            if longitude_ref.values != 'E':
                lon_value = -lon_value
        else:
            return []
        return [lat_value, lon_value]
