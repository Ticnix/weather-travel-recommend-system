from fastapi import FastAPI

app = FastAPI(title="气象出行推荐后端API")

@app.get("/")
async def root():
    return {"msg":"FastAPI服务启动成功"}