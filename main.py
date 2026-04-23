import os
import uvicorn
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import database
import auth
from config import BASE_DIR, STATIC_DIR, TEMPLATES_DIR, CV_DIR, LOGO_PATH

CV_DIR.mkdir(parents=True, exist_ok=True)
database.init_db()

app = FastAPI(title="FIRECODE CV Generator")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ── Helpers ────────────────────────────────────────────────────────────────

def _redirect_login():
    return RedirectResponse("/login", status_code=302)


def _require_admin(request: Request):
    user = auth.get_current_user(request)
    if not user:
        return _redirect_login()
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Только администратор")
    return user


# ── Auth ───────────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if auth.get_current_user(request):
        return RedirectResponse("/", status_code=302)
    csrf = auth.generate_csrf_token()
    return templates.TemplateResponse("login.html", {"request": request, "csrf": csrf, "error": None})


@app.post("/login")
async def login_post(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
):
    if not auth.verify_csrf_token(csrf_token):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Недействительный токен", "csrf": auth.generate_csrf_token()},
            status_code=400,
        )
    user = database.get_user_by_login(login)
    if not user or not auth.verify_password(password, user["password_hash"]):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный логин или пароль", "csrf": auth.generate_csrf_token()},
            status_code=401,
        )
    database.update_last_login(user["id"])
    token = auth.create_session(user["id"], user["role"])
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie("session", token, httponly=True, max_age=28800, samesite="lax")
    return resp


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("session")
    return resp


# ── Main CV Routes ─────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = auth.get_current_user(request)
    if not user:
        return _redirect_login()
    cvs = database.list_cvs()
    return templates.TemplateResponse("index.html", {
        "request": request, "user": user, "cvs": cvs,
    })


@app.post("/api/generate")
async def api_generate(request: Request):
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    body = await request.json()
    prompt = body.get("prompt", "").strip()
    if not prompt:
        return JSONResponse({"error": "Промпт не может быть пустым"}, status_code=400)

    api_key = database.get_setting("deepseek_api_key")
    model = database.get_setting("deepseek_model") or "deepseek-chat"
    if not api_key:
        return JSONResponse(
            {"error": "API ключ не настроен. Перейдите в /admin/settings"},
            status_code=400,
        )

    from cv_generator import generate_cv_data, generate_docx

    try:
        cv_data = await generate_cv_data(prompt, api_key, model)
    except Exception as e:
        return JSONResponse({"error": f"Ошибка DeepSeek API: {str(e)}"}, status_code=502)

    cv_id_temp = database.create_cv(user["id"], prompt, cv_data, "")
    docx_path = str(CV_DIR / f"cv_{cv_id_temp}.docx")

    try:
        generate_docx(cv_data, docx_path, str(LOGO_PATH))
    except Exception as e:
        database.delete_cv(cv_id_temp)
        return JSONResponse({"error": f"Ошибка генерации docx: {str(e)}"}, status_code=500)

    database.update_cv(cv_id_temp, cv_data, docx_path)
    database.log_action(user["id"], "generate", cv_id_temp, cv_data.get("name", ""))
    return JSONResponse({"id": cv_id_temp, "redirect": f"/cv/{cv_id_temp}"})


@app.get("/api/cvs")
async def api_list_cvs(
    request: Request,
    name: str = "",
    spec: str = "",
    stack: str = "",
    sort: str = "desc",
):
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    cvs = database.list_cvs(name=name, spec=spec, stack=stack, sort=sort)
    result = [
        {
            "id": c["id"],
            "name": c["name"],
            "specialization": c["specialization"],
            "languages": c["languages"],
            "frameworks": c["frameworks"],
            "created_at": c["created_at"],
            "updated_at": c["updated_at"],
        }
        for c in cvs
    ]
    return JSONResponse(result)


@app.get("/cv/{cv_id}", response_class=HTMLResponse)
async def cv_detail(request: Request, cv_id: int):
    user = auth.get_current_user(request)
    if not user:
        return _redirect_login()
    cv = database.get_cv(cv_id)
    if not cv:
        raise HTTPException(status_code=404, detail="CV не найден")
    return templates.TemplateResponse("cv_detail.html", {
        "request": request, "user": user, "cv": cv,
    })


# ── CV Mutations ───────────────────────────────────────────────────────────

@app.put("/api/cvs/{cv_id}")
async def api_update_cv(request: Request, cv_id: int):
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    cv = database.get_cv(cv_id)
    if not cv:
        return JSONResponse({"error": "Не найден"}, status_code=404)

    from cv_generator import generate_docx

    body = await request.json()
    if "projects" not in body:
        body["projects"] = cv["projects"]
    docx_path = str(CV_DIR / f"cv_{cv_id}.docx")
    try:
        generate_docx(body, docx_path, str(LOGO_PATH))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    database.update_cv(cv_id, body, docx_path)
    database.log_action(user["id"], "edit", cv_id, body.get("name", ""))
    return JSONResponse({"ok": True})


@app.post("/api/cvs/{cv_id}/regen-field")
async def api_regen_field(request: Request, cv_id: int):
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    body = await request.json()
    field = body.get("field", "")
    hint = body.get("hint", "")
    context = body.get("context", {})

    api_key = database.get_setting("deepseek_api_key")
    model = database.get_setting("deepseek_model") or "deepseek-chat"
    if not api_key:
        return JSONResponse({"error": "API ключ не настроен"}, status_code=400)

    from cv_generator import regen_field

    try:
        value = await regen_field(field, context, hint, api_key, model)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)

    database.log_action(user["id"], "regen_field", cv_id, field)
    return JSONResponse({"value": value})


@app.get("/api/cvs/{cv_id}/download")
async def api_download(request: Request, cv_id: int):
    user = auth.get_current_user(request)
    if not user:
        return _redirect_login()
    cv = database.get_cv(cv_id)
    if not cv:
        raise HTTPException(status_code=404)
    if not cv["docx_path"] or not os.path.exists(cv["docx_path"]):
        raise HTTPException(status_code=404, detail="Файл не найден")
    database.log_action(user["id"], "download", cv_id, cv["name"])
    filename = f"{cv['name']} - {cv['specialization']}.docx"
    return FileResponse(
        cv["docx_path"],
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )


@app.delete("/api/cvs/{cv_id}")
async def api_delete_cv(request: Request, cv_id: int):
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if user["role"] != "admin":
        return JSONResponse({"error": "Только администратор"}, status_code=403)
    cv = database.get_cv(cv_id)
    if not cv:
        return JSONResponse({"error": "Не найден"}, status_code=404)
    if cv["docx_path"] and os.path.exists(cv["docx_path"]):
        os.remove(cv["docx_path"])
    database.delete_cv(cv_id)
    database.log_action(user["id"], "delete", cv_id, cv["name"])
    return JSONResponse({"ok": True})


# ── Admin Routes ───────────────────────────────────────────────────────────

@app.get("/admin")
async def admin_redirect(request: Request):
    user = _require_admin(request)
    if not isinstance(user, dict):
        return user
    return RedirectResponse("/admin/stats", status_code=302)


@app.get("/admin/stats", response_class=HTMLResponse)
async def admin_stats(request: Request):
    user = _require_admin(request)
    if not isinstance(user, dict):
        return user
    stats = database.get_stats()
    return templates.TemplateResponse("admin/stats.html", {
        "request": request, "user": user, "stats": stats,
    })


@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request):
    user = _require_admin(request)
    if not isinstance(user, dict):
        return user
    users = database.list_users()
    csrf = auth.generate_csrf_token()
    return templates.TemplateResponse("admin/users.html", {
        "request": request, "user": user, "users": users, "csrf": csrf, "error": None,
    })


@app.post("/admin/users")
async def admin_create_user(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    role: str = Form("user"),
    csrf_token: str = Form(...),
):
    user = _require_admin(request)
    if not isinstance(user, dict):
        return user
    if not auth.verify_csrf_token(csrf_token):
        raise HTTPException(status_code=400, detail="Invalid CSRF")
    if database.get_user_by_login(login):
        users = database.list_users()
        return templates.TemplateResponse("admin/users.html", {
            "request": request, "user": user, "users": users,
            "error": f"Пользователь «{login}» уже существует",
            "csrf": auth.generate_csrf_token(),
        })
    pw_hash = auth.hash_password(password)
    database.create_user(login, pw_hash, role)
    return RedirectResponse("/admin/users", status_code=302)


@app.post("/admin/users/{user_id}/password")
async def admin_change_password(
    request: Request,
    user_id: int,
    new_password: str = Form(...),
    csrf_token: str = Form(...),
):
    user = _require_admin(request)
    if not isinstance(user, dict):
        return user
    if not auth.verify_csrf_token(csrf_token):
        raise HTTPException(status_code=400, detail="Invalid CSRF")
    pw_hash = auth.hash_password(new_password)
    database.update_user_password(user_id, pw_hash)
    return RedirectResponse("/admin/users", status_code=302)


@app.delete("/admin/users/{user_id}")
async def admin_delete_user(request: Request, user_id: int):
    user = _require_admin(request)
    if not isinstance(user, dict):
        return user
    current_user = auth.get_current_user(request)
    if current_user and current_user["id"] == user_id:
        return JSONResponse({"error": "Нельзя удалить себя"}, status_code=400)
    database.delete_user(user_id)
    return JSONResponse({"ok": True})


@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings(request: Request):
    user = _require_admin(request)
    if not isinstance(user, dict):
        return user
    api_key = database.get_setting("deepseek_api_key")
    model = database.get_setting("deepseek_model")
    csrf = auth.generate_csrf_token()
    return templates.TemplateResponse("admin/settings.html", {
        "request": request, "user": user,
        "api_key": api_key, "model": model, "csrf": csrf,
    })


@app.post("/admin/settings")
async def admin_settings_save(
    request: Request,
    deepseek_api_key: str = Form(...),
    deepseek_model: str = Form("deepseek-chat"),
    csrf_token: str = Form(...),
):
    user = _require_admin(request)
    if not isinstance(user, dict):
        return user
    if not auth.verify_csrf_token(csrf_token):
        raise HTTPException(status_code=400, detail="Invalid CSRF")
    database.set_setting("deepseek_api_key", deepseek_api_key, user["id"])
    database.set_setting("deepseek_model", deepseek_model, user["id"])
    return RedirectResponse("/admin/settings", status_code=302)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
