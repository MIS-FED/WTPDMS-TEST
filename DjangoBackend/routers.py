# routers.py
class PathBasedDatabaseRouter:
    def db_for_read(self, model, **hints):
        return self._get_db_from_request(hints)

    def db_for_write(self, model, **hints):
        return self._get_db_from_request(hints)

    def _get_db_from_request(self, hints):
        request = hints.get('request')
        if not request:
            return None

        if request.path.startswith('/tsl/'):
            return 'tsl_db'
        elif request.path.startswith('/api/'):
            return 'default'
        return None