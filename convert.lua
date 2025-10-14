local lunajson = require 'lunajson'
local serpent = require 'serpent'

file, err = io.open('data/sources.json', 'r')
if not file then
  print("Error opening file: " .. err)
  os.exit(1)
end

local content = file:read('*a')
file:close()
local data = lunajson.decode(content)

local  outfile, err = io.open('data/sources.lua', 'w')
if not outfile then
  print("Error opening file for writing: " .. err)
  os.exit(1)
end

outfile:write(serpent.block(data, {comment = false}))
outfile:close()