from database import *

def analyze_data():
    # analysis
    maker_query = EXIFData.select(EXIFData.maker, fn.COUNT(EXIFData.id).alias('count')).group_by(EXIFData.maker)
    no_maker = Photo.select().where(Photo.exif_data.is_null(True)).count()
    print('summary of makers: ')
    for row in maker_query:
        print(row.maker, row.count)
    print('NONE', no_maker)

if __name__ == '__main__':
    if db.is_closed():
        db.connect()
    analyze_data()