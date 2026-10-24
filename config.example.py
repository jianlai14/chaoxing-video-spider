# -*- coding: utf-8 -*-
"""配置模板：复制为 config.py 并填入你自己的 Cookie。
   config.py 已被 .gitignore 排除，不要提交真实 Cookie。

   取 Cookie：Chrome 打开课程任一章节 -> F12 -> Network -> 刷新 ->
   点第一个 studentstudy 请求 -> Request Headers -> 复制 cookie 整行的值。
   有效期参考 p_auth_token（JWT）里的 exp 字段。
"""

COOKIES = {
    "fid": "",
    "xxtenc": "",
    "_uid": "",
    "_d": "",
    "UID": "",
    "vc3": "",
    "uf": "",
    "cx_p_token": "",
    "p_auth_token": "",
    "DSSTASH_LOG": "",
    "spaceFid": "",
    "spaceRoleId": "",
    "tl": "",
    "k8s": "",
    "route": "",
    "writenote": "",
    "jrose": "",
}

# ===== 课程参数（来自章节页 URL 的 query）=====
COURSE_ID = "100000001"        # courseId
CLAZZ_ID = "100000002"         # clazzid
CPI = "100000003"              # cpi
CHAPTER_ID = "100000004"      # chapterId
ENC = "00000000000000000000000000000001"       # enc
OPENC = "00000000000000000000000000000001"     # openc
