import json
import redis

from arkos.utilities.errors import ConnectionError


class Storage:
    def __init__(self):
        self.connect()

    def connect(self):
        # Connect to Redis server
        try:
            self.redis = redis.Redis(unix_socket_path="/tmp/arkos-redis.sock")
            self.redis.ping()
            self.redis.flushdb()
        except redis.exceptions.ConnectionError, e:
            raise ConnectionError("arkOS Redis")

    def disconnect(self):
        # Disconnect from Redis server
        self.redis.flushdb()
        self.redis.connection_pool.disconnect()

    def check(self):
        # Make sure our connection to Redis is still active
        # If not, stop everything, reconnect and reload
        try:
            self.redis.ping()
        except:
            self.connect()

    def get(self, key, optkey=None):
        self.check()
        if optkey:
            return self._get(self.redis.hget("arkos:%s" % key, optkey))
        else:
            return self._get(self.redis.get("arkos:%s" % key))
    
    def get_all(self, key):
        values = self.redis.hgetall("arkos:%s" % key)
        for x in values:
            values[x] = self._get(values[x])
        return values

    def set(self, key, value, optval=None, pipe=None):
        self.check()
        r = pipe or self.redis
        if optval:
            r.hset("arkos:%s" % key, value, optval)
        elif type(value) == list:
            for x in enumerate(value):
                if type(x[1]) in [list, dict]:
                    value[x[0]] = json.dumps(x[1])
            r.rpush("arkos:%s" % key, *value)
        elif type(value) == dict:
            for x in value:
                if type(value[x]) in [list, dict]:
                    value[x] = json.dumps(value[x])
            r.hmset("arkos:%s" % key, value)
        else:
            r.set("arkos:%s" % key, value)
    
    def pop(self, key, pipe=None):
        r = pipe or self.redis
        return self._get(r.lpop("arkos:%s" % key))

    def get_list(self, key):
        self.check()
        values = []
        for x in self.redis.lrange("arkos:%s" % key, 0, -1):
            values.append(self._get(x))
        return values

    def append(self, key, value, pipe=None):
        self.check()
        r = pipe or self.redis
        if type(value) in [list, dict]:
            value = json.dumps(value)
        r.rpush("arkos:%s" % key, value)

    def append_all(self, key, values, pipe=None):
        if values:
            r = pipe or self.redis.pipeline()
            self.check()
            values = list(values)
            for x in enumerate(values):
                if type(x[1]) in [list, dict]:
                    values[x[0]] = json.dumps(x[1])
            r.rpush("arkos:%s" % key, *values)
            if not pipe:
                r.execute()
    
    def set_list(self, key, values, pipe=None):
        if values:
            r = pipe or self.redis.pipeline()
            r.delete("arkos:%s" % key)
            self.append_all(key, values, pipe=r)
            if not pipe:
                r.execute()
    
    def sortlist_add(self, key, priority, value, pipe=None):
        self.check()
        r = pipe or self.redis
        if type(value) in [list, dict]:
            value = json.dumps(value)
        r.zadd("arkos:%s" % key, value, priority)
    
    def sortlist_getbyscore(self, key, priority, num=0, pop=False):
        self.check()
        data = self.redis.zrevrangebyscore("arkos:%s" % key, priority, num)
        if pop:
            self.redis.zremrangebyscore("arkos:%s" % key, num, priority)
        return self._get(data)

    def remove(self, key, value, pipe=None):
        r = pipe or self.redis
        newvals = []
        for x in self.get_list(key):
            x = self._get(x)
            if x == value:
                continue
            newvals.append(x)
        self.delete(key, pipe=r)
        self.append_all(newvals, pipe=r)

    def remove_all(self, key, values, pipe=None):
        r = pipe or self.redis
        newvals = []
        for x in self.get_list(key):
            x = self._get(x)
            if x in values:
                continue
            newvals.append(x)
        self.delete(key, pipe=r)
        self.append_all(newvals, pipe=r)

    def delete(self, key, pipe=None):
        self.check()
        r = pipe or self.redis
        r.delete("arkos:%s" % key)

    def scan(self, key):
        return self.redis.scan(0, "arkos:%s" % key)[1]
    
    def pipeline(self):
        return self.redis.pipeline()
    
    def execute(self, pipe):
        pipe.execute()
    
    def expire(self, key, time, pipe=None):
        r = pipe or self.redis
        r.expire("arkos:%s" % key, time)
    
    def _get(self, value):
        if type(value) == str:
            return self._translate(value)
        elif type(value) == list:
            vals = []
            for x in value:
                vals.append(self._translate(x))
            return vals
        return value
    
    def _translate(self, value):
        if value.startswith(("[", "{")) and value.endswith(("]", "}")):
            return json.loads(value)
        return value


storage = Storage()
