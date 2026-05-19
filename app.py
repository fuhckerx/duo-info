from flask import Flask, jsonify, request
import time
import requests
import urllib3
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import SpecialFriend_pb2

urllib3.disable_warnings()

app = Flask(__name__)

# ── Config ──────────────────────────────────────────
GUEST_UID      = "4852597140"
GUEST_PASSWORD = "FuhX_FF_QXPP"
AeSkEy         = b'Yg&tc%DEuh6%Zc^8'
AeSiV          = b'6oyZDr22E3ychjM%'
BASE_URL       = "https://clientbp.ggpolarbear.com"


# ── Crypto ───────────────────────────────────────────
def enc(d):
    return AES.new(AeSkEy, AES.MODE_CBC, AeSiV).encrypt(pad(d, 16))

def dec(d):
    try:
        return unpad(AES.new(AeSkEy, AES.MODE_CBC, AeSiV).decrypt(d), 16)
    except Exception:
        return d


# ── Helpers ──────────────────────────────────────────
def build_uid_protobuf(uid: str) -> bytes:
    def to_varint(n):
        res = bytearray()
        while n >= 0x80:
            res.append((n & 0x7F) | 0x80)
            n >>= 7
        res.append(n)
        return bytes(res)
    return enc(b"\x08" + to_varint(int(uid)))


def format_timestamp(ts):
    try:
        return time.strftime('%B %d, %Y at %I:%M %p', time.localtime(ts))
    except Exception:
        return "Invalid Timestamp"


def fetch_jwt_token() -> str | None:
    url = f"https://ff-jwt-gen-api.lovable.app/api/public/token?uid={GUEST_UID}&password={GUEST_PASSWORD}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.json().get("token")
    except Exception:
        pass
    return None


def decode_protobuf_data(binary_data):
    try:
        if not binary_data or len(binary_data) < 2:
            return None, "Empty Response"

        response = SpecialFriend_pb2.SpecialFriendResponse()
        response.ParseFromString(binary_data)

        if not response.HasField("duo_info"):
            return None, "No Dynamic Duo info found"

        duo   = response.duo_info
        score = duo.score

        if   score < 101:  level = 1
        elif score < 301:  level = 2
        elif score < 501:  level = 3
        elif score < 801:  level = 4
        elif score < 1201: level = 5
        else:              level = 6

        status = "Active" if getattr(duo, "status", 0) == 2 else "Inactive"

        return {
            "partner_uid":          str(duo.partner_uid),
            "intimacy_score":       score,
            "duo_level":            f"Level {level}",
            "days_active":          duo.days_active,
            "created_on":           format_timestamp(duo.creation_timestamp),
            "creation_timestamp":   duo.creation_timestamp,
            "duo_status":           status,
        }, "Success"

    except Exception as e:
        return None, f"Parsing Error: {e}"


# ── API Route ─────────────────────────────────────────
@app.route("/info")
def info():
    uid = request.args.get("uid", "").strip()

    # Validate UID
    if not uid:
        return jsonify({
            "status":  "error",
            "message": "UID parameter is required. Usage: /info?uid=YOUR_UID"
        }), 400

    if not uid.isdigit():
        return jsonify({
            "status":  "error",
            "message": "UID must contain only numbers."
        }), 400

    # Step 1 – JWT token
    jwt = fetch_jwt_token()
    if not jwt:
        return jsonify({
            "status":  "error",
            "message": "Failed to generate API token. Try again later."
        }), 503

    # Step 2 – Fetch from game server
    headers = {
        "Authorization":  f"Bearer {jwt}",
        "Content-Type":   "application/x-www-form-urlencoded",
        "User-Agent":     "Dalvik/2.1.0 (Linux; U; Android 11)",
        "X-GA":           "v1 1",
        "ReleaseVersion": "OB53",
        "Connection":     "Keep-Alive",
    }

    try:
        payload  = build_uid_protobuf(uid)
        resp     = requests.post(
            f"{BASE_URL}/GetSpecialFriendList",
            headers=headers,
            data=payload,
            timeout=15,
            verify=False,
        )
    except Exception as e:
        return jsonify({
            "status":  "error",
            "message": f"Connection error: {e}"
        }), 500

    if resp.status_code == 500:
        return jsonify({
            "status":  "error",
            "message": "Invalid UID, private profile, or expired token."
        }), 404

    if resp.status_code != 200:
        return jsonify({
            "status":  "error",
            "message": f"Unexpected server response: HTTP {resp.status_code}"
        }), 502

    # Step 3 – Decrypt & parse protobuf
    decrypted  = dec(resp.content)
    data, msg  = decode_protobuf_data(decrypted)

    if not data:
        return jsonify({
            "status":  "error",
            "message": msg
        }), 404

    # Step 4 – Return success
    return jsonify({
        "status":  "success",
        "message": "DUO DETAILS RETRIEVED",
        "uid":     uid,
        "data": {
            "partner_uid":    data["partner_uid"],
            "intimacy_score": data["intimacy_score"],
            "duo_level":      data["duo_level"],
            "days_active":    f"{data['days_active']} Days",
            "created_on":     data["created_on"],
            "duo_status":     data["duo_status"],
        }
    })


# ── Root ──────────────────────────────────────────────
@app.route("/")
def index():
    return jsonify({
        "api":     "FF Dynamic DUO Info API",
        "version": "1.0",
        "usage":   "/info?uid=YOUR_UID",
        "example": "/info?uid=2355294066",
        "author":  "@ F X FuhX"
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
    
