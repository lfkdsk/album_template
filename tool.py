
from PIL import Image, ImageOps
import exifread
import os
from database import *
from datetime import datetime
import os
from shapely.geometry import Point, shape
import fiona  # 用于读取 Shapefile

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

# "exif_data": {
#   "Image Make": "Apple",
#   "Image Model": "iPhone 12 Pro",
#   "EXIF ExposureTime": "1/99s",
#   "EXIF FNumber": "F2",
#   "EXIF ISOSpeedRatings": "ISO 32",
#   "EXIF DateTimeOriginal": "2023:06:05 12:31:40",
#   "EXIF LensModel": "iPhone 12 Pro back triple camera 6mm f/2"
# }
def to_exif_date(data) -> EXIFData:
    if not data:
        return
    exif, _ = EXIFData.get_or_create(
        maker=data.get('Image Make'),
        model=data.get('Image Model'),
        exposure_time=data.get('EXIF ExposureTime', ''),
        f_number=data.get('EXIF FNumber', ''),
        iso=data.get('EXIF ISOSpeedRatings', ''),
        focal_length=data.get('EXIF FocalLength', ''),
        date=datetime.strptime(data.get('EXIF DateTimeOriginal', ''), '%Y:%m:%d %H:%M:%S'),
        lens_model=data.get('EXIF LensModel', '')
    )
    return exif

def get_country(lo, hi):
    with fiona.open('ne_110m_admin_0_countries.shp') as records:
        for record in records:
            point = Point(lo, hi)
            country_shape = shape(record['geometry'])
            if country_shape.contains(point):
                return record['properties']['NAME']
    return ''

def to_location(photo_model, data) -> Location:
    if not data:
        return
    if photo_model:
        return photo_model.location
    lo, hi = data[0], data[1]
    return Location.get_or_create(
        lo=lo, 
        hi=hi, 
        country=get_country(hi, lo)
    )