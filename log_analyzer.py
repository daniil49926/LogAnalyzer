import argparse
import fnmatch
import gzip
import json
import logging
import os
from string import Template
from typing import Dict, List, Tuple

config = {"REPORT_SIZE": 1000, "REPORT_DIR": "./reports", "LOG_DIR": "./log"}


def find_last_log() -> str:
    current_dir: str = os.path.dirname(__file__)
    log_files: List[str] = []
    mask: str = "nginx-access-ui.log-????????.gz"

    last_date: int = 0
    last_log_file: str = ""

    for i_files in os.listdir(current_dir + config["LOG_DIR"]):
        if fnmatch.fnmatch(i_files, mask) is True:
            log_files.append(config["LOG_DIR"] + "/" + i_files)

    for i_date in log_files:
        if i_date[-11:-3].isnumeric() and int(i_date[-11:-3]) > last_date:
            last_date = int(i_date[-11:-3])
            last_log_file = i_date
    logging.info(
        f"Нашел последний лог тут {os.path.dirname(__file__) + last_log_file[1:]}"
    )
    return last_log_file


def read_last_log(last_log: str) -> str:

    with gzip.open(last_log, "r") as log_file:
        for line in log_file:
            yield bytes.decode(line[:-1], encoding="utf-8")


def parse_log_line(log_line: str) -> Tuple[str, str]:
    s_line = log_line.split(" ")
    return s_line[7], s_line[-1]


def add_perc_value_and_time(
    data: Dict[str, Dict[str, int | float]],
    time_data: Dict[str, List[float]],
    count_req: int,
    times: float,
) -> Dict[str, Dict[str, int | float]]:
    for i_url in data:
        data[i_url]["count_perc"] = round((data[i_url]["count"] / count_req) * 100, 3)
        data[i_url]["time_perc"] = round((data[i_url]["time_sum"] / times) * 100, 3)
    for i_time_url in time_data:
        data[i_time_url]["time_avg"] = round(
            sum(time_data[i_time_url]) / len(time_data[i_time_url]), 3
        )
        data[i_time_url]["time_med"] = round(
            time_data[i_time_url][len(time_data[i_time_url]) // 2], 3
        )
    logging.info("Добавил в данные для отчета среднее время запроса и медиану")
    return data


def generate_report_path(log_rel_path: str) -> str:
    report_date: str = log_rel_path[-11:-3]
    report_full_path: str = (
        os.path.dirname(__file__)
        + config["REPORT_DIR"][1:]
        + "/"
        + "report-{}.{}.{}.html".format(
            report_date[:4], report_date[4:6], report_date[6:]
        )
    )
    return report_full_path


def generate_report(
    stat_data: Dict[str, Dict[str, int | float]], report_path: str
) -> None:
    logging.info("Начал формировать репорт")
    stat_data = sorted(stat_data.items(), key=lambda x: x[1]["time_avg"], reverse=True)[
        : config["REPORT_SIZE"]
    ]

    ins_data: List = [
        {
            "url": key,
            "count": val["count"],
            "count_perc": val["count_perc"],
            "time_avg": val["time_avg"],
            "time_max": val["time_max"],
            "time_med": val["time_med"],
            "time_perc": val["time_perc"],
            "time_sum": val["time_sum"],
        }
        for key, val in stat_data
    ]

    if ins_data is None:
        ins_data = []
    try:
        with open(config["REPORT_DIR"] + "/report.html", "rb") as template_file:
            template_string = template_file.read().decode("utf8")
            template = Template(template_string)
    except FileNotFoundError as _:
        logging.exception(
            f"Не нашел файл шаблона. Искал относительно скрипта {config['REPORT_DIR'] + '/report.html'}"
        )
    logging.info("Прочитал шаблон репорта")
    rendered = template.safe_substitute(table_json=json.dumps(ins_data))

    try:
        with open(report_path, "wb") as render_target:
            rendered = rendered.encode("utf8")
            render_target.write(rendered)
    except FileNotFoundError as _:
        logging.exception(f"Не смог создать файл репорта тут {report_path}")
    logging.info("Репорт готов")


def main() -> None:
    stat: Dict[str, Dict[str, int | float]] = {}
    total_count_request: int = 0
    total_time_requests: float = 0.0
    temp_time: Dict[str, List[float]] = {}
    log_path: str = find_last_log()
    report_path: str = generate_report_path(log_path)
    if not os.path.isfile(report_path):
        for i_line in read_last_log(log_path):
            url, request_time = parse_log_line(i_line)
            if url in stat:
                stat[url]["count"] += 1
                stat[url]["time_sum"] += float(request_time)
                if stat.get(url)["time_max"] < float(request_time):
                    stat[url]["time_max"] = float(request_time)
                temp_time[url].append(float(request_time))
            else:
                stat[url] = {
                    "count": 1,
                    "time_max": float(request_time),
                    "time_sum": float(request_time),
                }
                temp_time[url] = [
                    float(request_time),
                ]
            total_count_request += 1
            total_time_requests += float(request_time)
        stat = add_perc_value_and_time(
            data=stat,
            time_data=temp_time,
            count_req=total_count_request,
            times=total_time_requests,
        )
        generate_report(stat, report_path)
        logging.info(f"ОК. Путь до репорта {report_path}")
    else:
        logging.info(f"Лог обрабатывался раньше")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--config", help="Config file path")
    args = parser.parse_args()

    logging.basicConfig(
        filename="./analyzer.log",
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%Y.%m.%d %H:%M:%S",
    )

    if args.config:
        with open(args.config, "rb") as conf_file:
            config = json.load(conf_file)
    try:
        main()
    except BaseException as e:
        logging.exception(f"{e}")
