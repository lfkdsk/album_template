from peewee import *
from datetime import datetime
import os
from shapely.geometry import Point, shape
import fiona  # 用于读取 Shapefile

db = SqliteDatabase('sqlite.db')

class BaseModel(Model):
    class Meta:
        database = db


class Album(BaseModel):
    dir = CharField(unique=True)


class Location(BaseModel):
    lo = DoubleField()
    hi = DoubleField()
    country = CharField()

class EXIFData(BaseModel):
    maker = CharField()
    model = CharField()
    exposure_time = CharField()
    f_number = CharField()
    iso = CharField()
    focal_length = CharField()
    date = DateTimeField(formats=['%Y:%m:%d %H:%M:%S'])
    lens_model = CharField()


class Photo(BaseModel):
    id = AutoField()
    path = CharField(unique=True)
    dir = ForeignKeyField(Album, backref='photos')
    exif = CharField()
    location = ForeignKeyField(Location, backref='photo', null=True)
    name = CharField()
    desc = CharField()
    exif_data = ForeignKeyField(EXIFData, backref='photo', null=True)

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
    return EXIFData.create(
        maker=data.get('Image Make'),
        model=data.get('Image Model'),
        exposure_time=data.get('EXIF ExposureTime', ''),
        f_number=data.get('EXIF FNumber', ''),
        iso=data.get('EXIF ISOSpeedRatings', ''),
        focal_length=data.get('EXIF FocalLength', ''),
        date=datetime.strptime(data.get('EXIF DateTimeOriginal', ''), '%Y:%m:%d %H:%M:%S'),
        lens_model=data.get('EXIF LensModel', '')
    )

def get_country(lo, hi):
    with fiona.open('ne_110m_admin_0_countries.shp') as records:
        for record in records:
            point = Point(lo, hi)
            country_shape = shape(record['geometry'])
            if country_shape.contains(point):
                return record['properties']['NAME']
    return ''

def to_location(data) -> Location:
    if not data:
        return
    lo, hi = data[0], data[1]
    return Location.create(
        lo=lo, 
        hi=hi, 
        country=get_country(hi, lo),
    )