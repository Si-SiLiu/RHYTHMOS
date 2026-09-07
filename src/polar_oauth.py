import json
import os
import secrets
import time
import urllib.parse
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, request, session
from requests.auth import HTTPBasicAuth

try:
    from .secure_token_store import TokenStoreError, token_store_for
except ImportError:
    from secure_token_store import TokenStoreError, token_store_for

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

CLIENT_ID = os.getenv("POLAR_CLIENT_ID")
CLIENT_SECRET = os.getenv("POLAR_CLIENT_SECRET")
REDIRECT_URI = os.getenv("POLAR_REDIRECT_URI", "http://localhost:5000/oauth2_callback")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")

AUTH_URL = "https://auth.polar.com/oauth/authorize"
TOKEN_URL = "https://auth.polar.com/oauth/token"

DATA_DIR = BASE_DIR / "data"
TOKEN_FILE = Path(os.getenv("POLAR_TOKEN_FILE", DATA_DIR / "polar_tokens.json"))
DATA_DIR.mkdir(exist_ok=True)

SCOPES = [
    "training_sessions:read",
    "activity:read",
    "sleep:read",
    "nightly_recharge:read",
    "continuous_samples:read",
    "profile:read",
    "sports:read",
]

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY or secrets.token_hex(32)


def get_missing_polar_config():
    missing = []
    if not CLIENT_ID:
        missing.append("POLAR_CLIENT_ID")
    if not CLIENT_SECRET:
        missing.append("POLAR_CLIENT_SECRET")
    return missing


@app.route("/")
def index():
    missing = get_missing_polar_config()
    if missing:
        return f"""
        <h2>RHYTHMOS｜律衡 - Polar 授权</h2>
        <p>Flask 服务已启动。</p>
        <p>请先在 .env 里填写：{", ".join(missing)}</p>
        """, 503

    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state

    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": state,
    }
    if SCOPES:
        params["scope"] = " ".join(SCOPES)

    auth_link = AUTH_URL + "?" + urllib.parse.urlencode(params)

    return f"""
    <h2>RHYTHMOS｜律衡 - Polar 授权</h2>
    <p>点击下面链接，登录 Polar Flow 并授权。</p>
    <a href="{auth_link}">授权 Polar Flow 数据访问</a>
    """


@app.route("/oauth2_callback")
def oauth2_callback():
    if get_missing_polar_config():
        return "请先在 .env 里填写 POLAR_CLIENT_ID 和 POLAR_CLIENT_SECRET。", 503

    if request.args.get("error"):
        safe_args = {
            key: value
            for key, value in request.args.items()
            if key != "code"
        }
        return f"""
        <h3>授权失败</h3>
        <p>Error: {request.args.get('error')}</p>
        <pre>{json.dumps(safe_args, ensure_ascii=False, indent=2)}</pre>
        """, 400

    code = request.args.get("code")
    state = request.args.get("state")

    if not code:
        return "没有收到 authorization code。"

    if state != session.get("oauth_state"):
        return "State 校验失败。请重新从首页开始授权。"

    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
        auth=HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        timeout=30,
    )

    if response.status_code >= 400:
        return f"""
        <h3>Token 获取失败</h3>
        <p>Status: {response.status_code}</p>
        <pre>{response.text}</pre>
        """

    token_data = response.json()
    token_data["expires_at"] = int(time.time()) + int(token_data.get("expires_in", 0)) - 60

    try:
        token_store_for(TOKEN_FILE).save(token_data)
    except TokenStoreError:
        return "Token 安全存储配置无效，请检查服务端环境变量。", 503

    return """
    <h2>Polar 授权成功！</h2>
    <p>Polar 凭据已安全保存到服务端。</p>
    <p>下一步可以使用 token 抓取训练和活动数据。</p>
    """


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
