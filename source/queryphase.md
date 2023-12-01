---
title: 查询用例
date: 2022-04-19
---

## Group all image maker

```sql
SELECT IFNULL(EXIFData.maker, 'NONE') AS maker, COUNT(*) AS count
FROM Photo
LEFT OUTER JOIN EXIFData ON Photo.exif_data_id = EXIFData.id
GROUP BY maker
ORDER BY maker
```

[TRY IT](query?sql=SELECT%20IFNULL(EXIFData.maker,%20%27NONE%27)%20AS%20maker,%20COUNT(*)%20AS%20count%20FROM%20Photo%20LEFT%20OUTER%20JOIN%20EXIFData%20ON%20Photo.exif_data_id%20=%20EXIFData.id%20GROUP%20BY%20maker%20ORDER%20BY%20maker)

## Group by focal length and order by count.

```sql
SELECT EXIFData.focal_length, COUNT(*) AS count
FROM Photo
LEFT OUTER JOIN EXIFData ON Photo.exif_data_id = EXIFData.id
WHERE Photo.exif_data_id IS NOT NULL OR Photo.exif <> ''
GROUP BY EXIFData.focal_length
ORDER BY CAST(EXIFData.focal_length as DOUBLE) DESC
```

[TRY IT](query?sql="SELECT%20EXIFData.focal_length,%20COUNT(*)%20AS%20count%20FROM%20Photo%20LEFT%20OUTER%20JOIN%20EXIFData%20ON%20Photo.exif_data_id%20=%20EXIFData.id%20WHERE%20Photo.exif_data_id%20IS%20NOT%20NULL%20OR%20Photo.exif%20<>%20%27%27%20GROUP%20BY%20EXIFData.focal_length%20ORDER%20BY%20CAST(EXIFData.focal_length%20as%20DOUBLE)%20DESC")

## Give me random 5 fujifilm picture

```sql
SELECT photo.*, exifdata.maker
FROM photo
LEFT OUTER JOIN exifdata
ON photo.exif_data_id = exifdata.id
WHERE photo.location_id NOT NULL AND
exifdata.maker = 'FUJIFILM' ORDER BY RANDOM() LIMIT 5;
```

[TRY IT](query?sql="SELECT%20photo.*,%20exifdata.maker%20FROM%20photo%20LEFT%20OUTER%20JOIN%20exifdata%20ON%20photo.exif_data_id%20=%20exifdata.id%20WHERE%20photo.location_id%20NOT%20NULL%20AND%20exifdata.maker%20=%20%27FUJIFILM%27%20ORDER%20BY%20RANDOM()%20LIMIT%205;")

## Get N group by F Number

```sql
SELECT id, path, name, desc, f_number, lo, hi
FROM (
  SELECT p.id, p.path, p.name, p.desc, e.f_number, l.lo, l.hi,
         ROW_NUMBER() OVER (PARTITION BY e.f_number ORDER BY p.id) AS row_num
  FROM photo p
  JOIN exifdata e ON p.exif_data_id = e.id
  LEFT JOIN location l ON p.location_id = l.id
) subquery
WHERE row_num <= 10;
```

[TRY IT](query?sql="SELECT%20id,%20path,%20name,%20desc,%20f_number,%20lo,%20hi%20FROM%20(%20SELECT%20p.id,%20p.path,%20p.name,%20p.desc,%20e.f_number,%20l.lo,%20l.hi,%20ROW_NUMBER()%20OVER%20(PARTITION%20BY%20e.f_number%20ORDER%20BY%20p.id)%20AS%20row_num%20FROM%20photo%20p%20JOIN%20exifdata%20e%20ON%20p.exif_data_id%20=%20e.id%20LEFT%20JOIN%20location%20l%20ON%20p.location_id%20=%20l.id%20)%20subquery%20WHERE%20row_num%20<=%2010;")

## Group by country 

```sql
SELECT country, COUNT(*) as count 
FROM location 
GROUP BY country
```

[TRY IT](query?sql="SELECT%20country,%20COUNT(*)%20as%20count%20FROM%20location%20GROUP%20BY%20country")