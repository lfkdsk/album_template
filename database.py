from peewee import *

db = SqliteDatabase('sqlite.db')

class BaseModel(Model):
    class Meta:
        database = db


class Album(BaseModel):
    dir = CharField(unique=True)

class Tag(BaseModel):
    name = CharField(unique=True)

class Location(BaseModel):
    lo = DoubleField()
    hi = DoubleField()
    country = CharField(null=True)

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
    tag = ForeignKeyField(Tag, backref='photos', null=True)
