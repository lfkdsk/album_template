from PIL import Image, ImageOps
import exifread
import os
from database import *
from datetime import datetime
from shapely.geometry import Point, shape
from shapely.prepared import prep
import fiona  # 用于读取 Shapefile
from PIL.ExifTags import TAGS

# input_file 可以是路径，也可以是 BytesIO（build 时原图直接从 git 对象库读进内存）。
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

def read_gps(exif_dict):
    """从 exifread.process_file 的结果里取 [lat, lon]，没有就返回 []。"""
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

def parse_exif_tags(tags):
    """把 exifread 的 tags 转成 (tag_text, exif_data, pure_exif_data)。

    exif_data 是带单位的展示值，pure_exif_data 是写进 EXIFData 表的原始值。
    """
    tag_text = ''
    exif_data = {}
    pure_exif_data = {}
    for tag in tags.keys():
        if tag in ['Image Make', 'Image Model', 'EXIF LensModel', 'EXIF FocalLength','EXIF FNumber', 'EXIF ISOSpeedRatings', 'EXIF ExposureTime', 'EXIF DateTimeOriginal']:
          pre = pro = cur = ''
          if tag == 'EXIF FNumber':
              pre = 'F'
              cur = str(round(eval(str(tags[tag])), 1))
          elif tag == 'EXIF ISOSpeedRatings':
              pre = 'ISO '
              cur = str(eval(str(tags[tag])))
          elif tag == 'EXIF ExposureTime':
              pro = 's'
              cur = str(tags[tag])
              resu = cur.split('/')
              # calc for iPhone with expo time like:
              if len(resu) == 2 and resu[0] != '1':
                a, b = eval(resu[0]), eval(resu[1])
                cur = f'{a/b}' if a > b else f'1/{int(b/a)}'
          elif tag == 'EXIF DateTimeOriginal':
              exif_data[tag] = pure_exif_data[tag] = str(tags[tag])
              continue
          elif tag == 'EXIF FocalLength':
              cur = str(round(eval(str(tags[tag])), 1))
              pro = 'mm'
          elif tag == 'Image Make':
              cur = str(tags[tag])
          else:
              cur = str(tags[tag])
          cur_text = pre + cur + pro
          exif_data[tag] = cur_text
          pure_exif_data[tag] = cur
          tag_text += cur_text
          tag_text += ' '
    return tag_text, exif_data, pure_exif_data

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
    if not data or data.get('Image Make', '') == '' or data.get('Image Model', '') == '':
        print("No enough EXIF data found", data)
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

_countries = None

def get_country(lo, hi):
    # shapefile 只读一次；prepared geometry 的 contains 和原始 shape 判定结果一致，只是更快。
    global _countries
    if _countries is None:
        shp = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ne_110m_admin_0_countries.shp')
        with fiona.open(shp) as records:
            _countries = [(prep(shape(record['geometry'])), record['properties']['NAME']) for record in records]
    point = Point(lo, hi)
    for country_shape, name in _countries:
        if country_shape.contains(point):
            return name
    return ''

def to_location(data, country) -> Location:
    if not data:
        return None
    lo, hi = data[0], data[1]
    return Location.create(
        lo=lo,
        hi=hi,
        country=country
    )


def get_exif_datetime(fp):
    """从 EXIF 读取拍摄时间，没有则返回 None"""
    try:
        with Image.open(fp) as img:
            exif = img._getexif()
            if exif:
                for tag_id, value in exif.items():
                    tag = TAGS.get(tag_id)
                    if tag == "DateTimeOriginal":
                        return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None

def sort_photos(files, meta):
    """files 是 [(文件名, blob sha)]，meta 是 manifest 里按 sha 缓存的元数据。"""
    def sort_key(item):
        filename, sha = item
        dt = meta.get(sha, {}).get('datetime')
        if dt:
            # 有时间的：先按时间，再按文件名
            return (0, datetime.strptime(dt, "%Y:%m:%d %H:%M:%S"), filename.lower())
        else:
            # 没时间的：放后面，按文件名
            return (1, filename.lower())

    return [filename for filename, _ in sorted(files, key=sort_key)]
