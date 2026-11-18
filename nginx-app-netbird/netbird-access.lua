local ubus = require "oui.ubus"

local sid = (ngx.var.http_cookie or ""):match("Admin%-Token=([^;%s]+)")
if not sid then
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

local res = ubus.call("gl-session", "touch", { sid = sid })
if type(res) ~= "table" or res.code ~= 0 then
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end
