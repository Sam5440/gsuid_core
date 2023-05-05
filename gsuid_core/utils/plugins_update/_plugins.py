from typing import Dict, List, Union, Optional

import aiohttp
from git.repo import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError

from gsuid_core.logger import logger

from .api import PLUGINS_PATH, proxy_url, plugins_lib

plugins_list: Dict[str, Dict[str, str]] = {}


async def refresh_list() -> List[str]:
    refresh_list = []
    async with aiohttp.ClientSession() as session:
        logger.info(f'稍等...开始刷新插件列表, 地址: {plugins_lib}')
        async with session.get(plugins_lib) as resp:
            _plugins_list: Dict[
                str, Dict[str, Dict[str, str]]
            ] = await resp.json()
            for i in _plugins_list['plugins']:
                if i.lower() not in plugins_list:
                    refresh_list.append(i)
                    logger.info(f'[刷新插件列表] 列表新增插件 {i}')
                plugins_list[i.lower()] = _plugins_list['plugins'][i]
    return refresh_list


async def get_plugins_list() -> Dict[str, Dict[str, str]]:
    if not plugins_list:
        await refresh_list()
    return plugins_list


async def get_plugins_url(name: str) -> Optional[Dict[str, str]]:
    if not plugins_list:
        await refresh_list()

    if name in plugins_list:
        return plugins_list[name]
    else:
        for _n in plugins_list:
            sim = len(set(_n) & set(name))
            if sim >= 0.5 * len(_n):
                return plugins_list[_n]
        else:
            return None


def install_plugins(plugins: Dict[str, str]) -> str:
    plugin_name = plugins['link'].split('/')[-1]
    git_path = f'{proxy_url}{plugins["link"]}.git'
    logger.info(f'稍等...开始安装插件, 地址: {git_path}')
    path = PLUGINS_PATH / plugin_name
    if path.exists():
        return '该插件已经安装过了!'
    Repo.clone_from(git_path, path, single_branch=True, depth=1)
    logger.info(f'插件{plugin_name}安装成功!')
    return f'插件{plugin_name}安装成功!发送[gs重启]以应用!'


async def install_plugin(plugin_name: str) -> int:
    url = await get_plugins_url(plugin_name)
    if url is None:
        return -1
    install_plugins(url)
    return 0


def check_plugins(plugin_name: str) -> Optional[Repo]:
    path = PLUGINS_PATH / plugin_name
    if path.exists():
        try:
            repo = Repo(path)
        except InvalidGitRepositoryError:
            return None
        return repo
    else:
        return None


def check_can_update(repo: Repo) -> bool:
    try:
        remote = repo.remote()  # 获取远程仓库
        remote.fetch()  # 从远程获取最新版本
    except GitCommandError as e:
        logger.error(f'发生Git命令错误{e}!')
        return False
    local_commit = repo.commit()  # 获取本地最新提交
    remote_commit = remote.fetch()[0].commit  # 获取远程最新提交
    if local_commit.hexsha == remote_commit.hexsha:  # 比较本地和远程的提交哈希值
        return False
    return True


def check_status(plugin_name: str) -> int:
    repo = check_plugins(plugin_name)
    if repo is None:
        return 3
    if check_can_update(repo):
        return 1
    else:
        return 4


def update_plugins(
    plugin_name: str,
    level: int = 0,
    log_key: List[str] = [],
    log_limit: int = 10,
) -> Union[str, List]:
    for _n in PLUGINS_PATH.iterdir():
        _name = _n.name
        sim = len(set(_name.lower()) & set(plugin_name.lower()))
        if sim >= 0.5 * len(_name):
            plugin_name = _name
            break

    repo = check_plugins(plugin_name)
    if not repo:
        return '更新失败, 不存在该插件!'
    o = repo.remotes.origin

    if level >= 2:
        logger.warning(f'[更新][{plugin_name}] 正在执行 git clean --xdf')
        repo.git.clean('-xdf')
    # 还原上次更改
    if level >= 1:
        logger.warning(f'[更新][{plugin_name}] 正在执行 git reset --hard')
        repo.git.reset('--hard')

    try:
        pull_log = o.pull()
        logger.info(f'[更新][{plugin_name}] {pull_log}')
    except GitCommandError as e:
        logger.warning(e)
        return '更新失败, 请检查控制台...'

    commits = list(repo.iter_commits(max_count=40))
    log_list = []
    for commit in commits:
        if isinstance(commit.message, str):
            if log_key:
                for key in log_key:
                    if key in commit.message:
                        log_list.append(commit.message.replace('\n', ''))
                        if len(log_list) >= log_limit:
                            break
            else:
                log_list.append(commit.message.replace('\n', ''))
                if len(log_list) >= log_limit:
                    break
    return log_list