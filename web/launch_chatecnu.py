"""Local interactive launcher. Token stays in process memory, never a file."""
import argparse
import getpass
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import webbrowser

import server

BASE_URL='https://chat.ecnu.edu.cn/open/api/v1'

def normalize_token(value):
    value=value.strip()
    if value.lower().startswith('bearer '):value=value[7:].strip()
    if not value or not value.isascii() or any(c.isspace() or ord(c)<33 or ord(c)==127 for c in value):
        raise ValueError('令牌应为完整的一行英数字符；请只复制令牌内容，不要复制说明文字或换行。')
    return value

def check_models(token,model):
    """Authenticated read only; does not submit a theorem or generate tokens."""
    request=Request(BASE_URL+'/models',headers={'Authorization':'Bearer '+token,'Accept':'application/json'})
    try:
        with urlopen(request,timeout=30) as r:
            raw=r.read(500001)
            if len(raw)>500000:raise ValueError('模型列表返回过大，请稍后重试。')
            value=json.loads(raw)
    except HTTPError as e:
        if e.code in (401,403):raise ValueError('令牌验证未通过：请在ChatECNU“我的令牌”确认令牌有效、未过期且有权限。')
        if e.code==429:raise ValueError('ChatECNU暂时限流，请稍后重新启动。')
        raise ValueError('ChatECNU模型列表请求失败（HTTP '+str(e.code)+'）；未进行模型分析。')
    except (URLError,TimeoutError,OSError):raise ValueError('无法连接ChatECNU，请检查网络，或平台是否要求学校网络/VPN，再重新启动。')
    except (json.JSONDecodeError,UnicodeDecodeError):raise ValueError('ChatECNU未返回可读取的模型列表，未进行模型分析。')
    if not isinstance(value,dict) or value.get('error') or not isinstance(value.get('data'),list):
        raise ValueError('ChatECNU模型列表格式异常，未将连接标为通过。')
    ids=[item.get('id') for item in value['data'] if isinstance(item,dict) and isinstance(item.get('id'),str)]
    if model not in ids:raise ValueError('当前令牌的模型列表不含 '+model+'。请在平台确认权限和模型调用名；未自动换用其他模型。')
    return True

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',default='ecnu-max',choices=['ecnu-max','ecnu-plus'])
    p.add_argument('--port',type=int,default=8765)
    args=p.parse_args()
    os.environ['CA_WEB_BASE_URL']=BASE_URL
    os.environ['CA_WEB_MODEL']=args.model
    os.environ['CA_WEB_API_MODE']='chat_completions'
    os.environ.setdefault('CA_WEB_MAX_OUTPUT_TOKENS','12000')
    os.environ.setdefault('CA_WEB_TIMEOUT_SECONDS','120')
    try:httpd=server.make_server('127.0.0.1',args.port)
    except OSError:
        print(f'端口 {args.port} 正被占用。请先关闭旧的网页启动窗口，或在旧窗口按Ctrl+C，再双击本启动文件。')
        print('如果旧服务由Codex后台启动，请让Codex停止旧的本机网页服务。没有停止或覆盖其他程序。')
        return 2
    try:
        print('条件考古学 · ChatECNU专用启动')
        print('地址已配置：'+BASE_URL+'；模型：'+args.model)
        print('请到 https://chat.ecnu.edu.cn 登录，左下角头像 → 我的令牌，复制API令牌。')
        print('令牌只在这个进程内存使用，不写入文件，不发送到聊天。关闭窗口后需要重新输入。')
        token=normalize_token(getpass.getpass('请粘贴令牌后按回车（不会显示字符）：'))
        print('正在读取模型列表验证令牌，不会提交定理或发起模型生成……',flush=True)
        check_models(token,args.model)
        os.environ['CA_WEB_API_KEY']=token
        print('令牌验证通过，且模型列表包含 '+args.model+'。这还不代表数学分析已测试通过。')
        address=f'http://127.0.0.1:{httpd.server_port}'
        print('网页地址：'+address)
        print('请保持此窗口打开。点击“开始真实分析”后才会向ChatECNU发送定理并消耗额度。',flush=True)
        try:
            if not webbrowser.open(address):print('未自动打开浏览器，请手工访问上面的网页地址。',flush=True)
        except (OSError,webbrowser.Error):
            print('未自动打开浏览器，请手工访问上面的网页地址。',flush=True)
        try:httpd.serve_forever()
        except KeyboardInterrupt:print('\n网页已停止。')
        return 0
    except (ValueError,EOFError) as e:
        print('未启动真实分析：'+str(e));return 2
    except KeyboardInterrupt:
        print('\n已取消。');return 2
    finally:
        httpd.server_close()
        os.environ.pop('CA_WEB_API_KEY',None)

if __name__=='__main__':raise SystemExit(main())
