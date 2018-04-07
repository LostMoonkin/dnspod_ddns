import requests
from logging import DEBUG, INFO, WARN, ERROR
import log
import json
from datetime import datetime
from time import sleep


def load_config():
    with open("./config.json", "r", encoding="utf-8") as f:
        config = json.load(f)
        return config


LOG = log.get_logger()
CONFIG = load_config()


def get_config(error_abort=True, *args):
    content = CONFIG
    for arg in args:
        content = content[arg]
        if content is None:
            if error_abort:
                LOG.error("Could not get %s in config, full args: %s" % (arg, args))
                exit(-1)
            else:
                return None
    return content


def get_real_ip():
    ip_servers = get_config(True, "ip_servers")
    for ip_server in ip_servers:
        r = requests.get(ip_server)
        if r.status_code != 200:
            handler_log(WARN, "Could not get real ip from [%s] http status: %d" % (ip_server, r.status_code))
        else:
            return r.text
    return None


def send_server_chan(text, message):
    prefix = get_config(False, "server_chan", "prefix")
    if prefix is None:
        prefix = "https://sc.ftqq.com/"
    url = prefix + get_config(True, "server_chan", "sc_key") + ".send"
    r = requests.post(url, {
        "text": text,
        "desp": message
    })
    if r.status_code != 200:
        LOG.error("Could not send message to server chan, http status: %d, text: %s" % (r.status_code, r.text))
    else:
        LOG.info("Send message to server chan, text: %s, message: %s" % (text, message))


def get_domain_id():
    domain, url, token = get_config(True, "dnspod", "domain"), get_config(True, "dnspod", "get_domain_list"), \
                         get_config(True, "dnspod", "api_token")
    r = requests.post(url, {
        "login_token": token,
        "format": "json"
    })
    if r.status_code != 200:
        handler_log(ERROR, "Connect to dnspod error, http status: %d." % r.status_code)
        return None
    content = json.loads(r.text)
    if content["status"]["code"] != "1":
        handler_log(ERROR, content["status"]["message"])
        return None
    for domain_info in content["domains"]:
        if domain == domain_info["name"]:
            return domain_info["id"]
    handler_log(ERROR, "Could not find domain in dnspod domain list, domain: %s, domain list: %s"
                % (domain, content["domains"]))
    return None


def create_record(ip):
    sub_domain, domain = get_config(False, "dnspod", "sub_domain"), get_config(True, "dnspod", "domain")
    if sub_domain is None or sub_domain == "":
        sub_domain = "@"
    r = requests.post(get_config(True, "dnspod", "create_record", {
        "login_token": get_config(True, "dnspod", "api_token"),
        "domain": domain,
        "sub_domain": sub_domain,
        "record_type": "A",
        "record_line": get_config(True, "dnspod", "record_line"),
        "value": ip,
        "format": "json"
    }))
    if r.status_code != 200:
        handler_log(ERROR, "Connect to dnspod error, http status: %d." % r.status_code)
        return None, False
    content = json.loads(r.text)
    if content["status"]["code"] != "1":
        handler_log(ERROR, content["status"]["message"])
        return None, False
    handler_log(INFO, "Create record successful. %s.%s to %s" % (sub_domain, domain, ip))
    return content["record"]["id"], True


def get_record_id(ip):
    sub_domain, domain = get_config(False, "dnspod", "sub_domain"), get_config(True, "dnspod", "domain")
    if sub_domain is None or sub_domain == "":
        sub_domain = "@"
    r = requests.post(get_config(True, "dnspod", "get_records"), {
        "login_token": get_config(True, "dnspod", "api_token"),
        "domain": domain,
        "format": "json"
    })
    if r.status_code != 200:
        handler_log(ERROR, "Connect to dnspod error, http status: %d." % r.status_code)
        return None, False
    content = json.loads(r.text)
    if content["status"]["code"] != "1":
        handler_log(ERROR, content["status"]["message"])
        return None, False
    for record in content["records"]:
        if record["name"] == sub_domain and record["type"] == "A":
            return record["id"], False
    handler_log(WARN, "Could not find sub domain record.")
    handler_log(INFO, "Try to create record.")
    return create_record(ip)


def modify_domain_record(ip, record_id):
    sub_domain, domain = get_config(False, "dnspod", "sub_domain"), get_config(True, "dnspod", "domain")
    if sub_domain is None or sub_domain == "":
        sub_domain = "@"
    r = requests.post(get_config(True, "dnspod", "modify_record"), {
        "login_token": get_config(True, "dnspod", "api_token"),
        "domain": domain,
        "sub_domain": sub_domain,
        "record_id": record_id,
        "record_type": "A",
        "record_line": get_config(True, "dnspod", "record_line"),
        "value": ip,
        "format": "json"
    })
    if r.status_code != 200:
        handler_log(ERROR, "Connect to dnspod error, http status: %d." % r.status_code)
        return False
    content = json.loads(r.text)
    if content["status"]["code"] != "1":
        handler_log(ERROR, content["status"]["message"])
        return False
    handler_log(INFO, "Success modify domain [%s.%s] to ip: %s" % (sub_domain, domain, ip))
    return True


def is_night():
    now = datetime.now()
    morning, evening = datetime(now.year, now.month, now.day, 8, 0, 0), datetime(now.year, now.month, now.day, 20, 0, 0)
    return now <= morning or now >= evening


def handler_log(level, message, need_record=False):
    LOG.log(level, message)
    mode = CONFIG["mode"]
    if mode == "DEBUG":
        send_server_chan("Debug", message)
    if (mode is None or mode == "NORMAL") and (level >= ERROR or need_record):
        send_server_chan("Error" if level >= ERROR else "Notice", message)
    if mode == "NIGHT" and not is_night():
        send_server_chan("Error", message)


def work():
    ip = ""
    interval = CONFIG["interval"] * 60 if CONFIG["interval"] is not None else 10 * 60
    while True:
        ip_now = get_real_ip()
        if ip != ip_now:
            handler_log(INFO, "Real ip was changed. [%s] -> [%s]" % (ip, ip_now), True)
            record_id, created = get_record_id(ip_now)
            if not created and record_id is not None:
                modified = modify_domain_record(ip_now, record_id)
                if modified:
                    ip = ip_now
            if created:
                ip = ip_now
        else:
            handler_log(INFO, "Real ip was same. [%s]" % ip)
        sleep(interval)
