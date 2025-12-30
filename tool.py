
from PIL import Image, ImageOps
import exifread
import os
from database import *
from datetime import datetime
import os
from shapely.geometry import Point, shape
import fiona  # 用于读取 Shapefile
from PIL.ExifTags import TAGS

def thumbnail_image(input_file, output_file, max_size=(1000, 1000), resample=3, ext='webp'):
    im = Image.open(input_file)
    im = ImageOps.exif_transpose(im)
    im.thumbnail(max_size, resample=resample, reducing_gap=3.0)
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
    if not data or len(data) != 8:
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
    if photo_model:
        return photo_model.location
    if not data:
        return None
    lo, hi = data[0], data[1]
    return Location.create(
        lo=lo,
        hi=hi,
        country=get_country(hi, lo)
    )


def get_exif_datetime(file_path):
    """从 EXIF 读取拍摄时间，没有则返回 None"""
    try:
        with Image.open(file_path) as img:
            exif = img._getexif()
            if exif:
                for tag_id, value in exif.items():
                    tag = TAGS.get(tag_id)
                    if tag == "DateTimeOriginal":
                        return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None

def sort_photos(folder):
    files = [f for f in os.listdir(folder)]

    def sort_key(filename):
        dt = get_exif_datetime(os.path.join(folder, filename))
        if dt:
            # 有时间的：先按时间，再按文件名
            return (0, dt, filename.lower())
        else:
            # 没时间的：放后面，按文件名
            return (1, filename.lower())

    return sorted(files, key=sort_key)
