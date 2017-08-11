import geohash
import ujson as json

from geodata.distance.haversine import haversine_distance


class PointIndexSpark(object):
    GEOHASH_PRECISION = 5
    sort_reverse = False

    @classmethod
    def point_geohashes(cls, geojson_ids, precision=None):
        if precision is None:
            precision = cls.GEOHASH_PRECISION
        return geojson_ids.map(lambda (key, rec): (geohash.encode(rec['geometry']['coordinates'][1], rec['geometry']['coordinates'][0])[:precision], key))

    @classmethod
    def indexed_point_geohashes(cls, geojson_ids, precision=None):
        if precision is None:
            precision = cls.GEOHASH_PRECISION
        geohash_ids = geojson_ids.mapValues(lambda rec: geohash.encode(rec['geometry']['coordinates'][1], rec['geometry']['coordinates'][0]))
        return geohash_ids.flatMap(lambda (key, full_gh): [(gh, key) for gh in geohash.expand(full_gh[:precision])])

    @classmethod
    def preprocess_geojson(cls, rec):
        return rec

    @classmethod
    def geojson_ids(cls, lines):
        geojson = lines.map(lambda line: json.loads(line.rstrip()))
        geojson_ids = geojson.zipWithIndex() \
                             .map(lambda (rec, uid): (uid, cls.preprocess_geojson(rec)))
        return geojson_ids

    @classmethod
    def distance_sort(cls, point):
        coords = point['geometry']['coordinates']
        lat, lon = coords[1], coords[0]

        def distance_to(other):
            other_coords = other['geometry']['coordinates']
            other_lat, other_lon = other_coords[1], other_coords[0]
            return haversine_distance(lat, lon, other_lat, other_lon)
        return distance_to

    @classmethod
    def nearby_points(cls, point_ids, indexed_point_ids, precision=None):
        indexed_point_geohashes = cls.indexed_point_geohashes(indexed_point_ids)
        point_geohashes = cls.point_geohashes(point_ids)

        nearby_points = indexed_point_geohashes.join(point_geohashes) \
                                               .values() \
                                               .join(indexed_point_ids) \
                                               .values() \
                                               .groupByKey() \
                                               .join(point_ids)

        return nearby_points.mapValues(lambda (indexed_points, point): (point, sorted(list(indexed_points), key=cls.distance_sort)))

    @classmethod
    def reverse_geocode(cls, point_ids, indexed_point_ids, precision=None):
        points_with_indexed = cls.nearby_points(point_ids, indexed_point_ids, precision=precision)

        all_points = point_ids.leftOuterJoin(points_with_indexed) \
                              .map(lambda (point_id, (point, indexed)): (point, indexed or []))

        return all_points