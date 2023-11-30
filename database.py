from peewee import *
from datetime import datetime
import os

db = SqliteDatabase('sqlite.db')

class BaseModel(Model):
    class Meta:
        database = db


class Album(BaseModel):
    dir = CharField(unique=True)


class Location(BaseModel):
    lo = DoubleField()
    hi = DoubleField()


class EXIFData(BaseModel):
    maker = CharField()
    model = CharField()
    exposure_time = CharField()
    f_number = CharField()
    iso = CharField()
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
        date=datetime.strptime(data.get('EXIF DateTimeOriginal', ''), '%Y:%m:%d %H:%M:%S'),
        lens_model=data.get('EXIF LensModel', '')
    )

def to_location(data) -> Location:
    if not data:
        return
    return Location.create(lo=data[0], hi=data[1])