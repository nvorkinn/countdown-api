local t = redis.call('TIME')
local now_ms = t[1] .. string.format('%03d', math.floor(t[2] / 1000))

if redis.call('SET', KEYS[1], now_ms, 'NX', 'PX', ARGV[2]) then
  redis.call('LPUSH', KEYS[2], ARGV[1])
  return 1
end
return 0
