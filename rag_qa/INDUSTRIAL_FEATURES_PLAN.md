# RAG_QA 工业化功能增强方案

## 一、四项功能的当前实现状态

### 1. 来源引用到段落/页码
**当前状态：部分实现**

已有：
- ✅ `view_sources.py` 可查看来源
- ✅ `vector_store.py` 返回 `source` 和 `timestamp` 字段
- ✅ `schemas.py` 的 `SourceDocument` 包含 `source` 和 `score`
- ✅ 检索结果包含 `parent_id` 和 `parent_content`

缺失：
- ❌ 没有 `page_num` 字段（无法精确到页码）
- ❌ 没有 `chunk_index` 字段（无法精确到段落）
- ❌ 回答时没有强制引用格式
- ❌ 前端没有引用卡片展示

**改造难度：中等（1-2天）**

---

### 2. 知识库版本管理
**当前状态：基本没有实现**

已有：
- ✅ 文档分类存储（`data/mining_data` 等）
- ✅ 文档处理流程（`document_processor.py`）
- ✅ 向量库支持 `source` 字段过滤

缺失：
- ❌ 没有版本号概念
- ❌ 没有文档元数据表（上传时间、来源、有效期）
- ❌ 没有审核流程
- ❌ 没有增量更新机制
- ❌ 没有回滚能力

**改造难度：较大（3-5天）**

---

### 3. 用户反馈闭环
**当前状态：有基础，但没有完整闭环**

已有：
- ✅ `conversation_manager.py` 保存问答记录
- ✅ 会话持久化到 JSON 文件
- ✅ 后端有 `/api/sessions` 路由
- ✅ 问答记录包含 `metadata` 字段

缺失：
- ❌ 没有反馈字段（满意度、是否正确、纠错内容）
- ❌ 没有反馈 API 端点
- ❌ 没有反馈统计
- ❌ 没有反馈进入优化流程

**改造难度：简单（1-2天）**

---

### 4. 权限控制与多角色访问
**当前状态：基本没有实现**

已有：
- ✅ FastAPI 后端结构清晰
- ✅ 多 router 分离（chat、sessions、knowledge 等）
- ✅ 前后端分离

缺失：
- ❌ 没有登录认证
- ❌ 没有 JWT / Token
- ❌ 没有角色定义
- ❌ 没有接口权限控制
- ❌ 没有审计日志

**改造难度：较大（3-5天）**

---

## 二、具体落地方案

### 方案 A：来源引用到段落/页码

#### 第一步：修改文档入库时的元数据
**文件：`core/document_processor.py`**

需要改造：
- 在 `process_documents()` 中，为每个 chunk 增加字段：
  - `page_num`：页码（从 PDF 元数据或文档结构提取）
  - `chunk_index`：段落序号
  - `doc_title`：文档标题
  - `section_name`：章节名

```python
# 示例改造
chunk.metadata.update({
    "page_num": page_number,
    "chunk_index": chunk_idx,
    "doc_title": doc_title,
    "section_name": section_name,
})
```

#### 第二步：修改向量库存储
**文件：`core/vector_store.py`**

在 `add_documents()` 中，增加字段到 Milvus schema：
```python
schema.add_field(field_name="page_num", datatype=DataType.INT32)
schema.add_field(field_name="chunk_index", datatype=DataType.INT32)
schema.add_field(field_name="doc_title", datatype=DataType.VARCHAR, max_length=500)
schema.add_field(field_name="section_name", datatype=DataType.VARCHAR, max_length=500)
```

在 `hybrid_search_with_rerank()` 中，返回这些字段：
```python
output_fields=["text", "parent_id", "parent_content", "source", "timestamp", 
               "page_num", "chunk_index", "doc_title", "section_name"]
```

#### 第三步：修改回答生成逻辑
**文件：`core/new_rag_system.py`**

在 `generate_answer()` 中，修改 prompt 要求模型引用：
```python
# 在 RAG prompt 中加入
rag_prompt = """
基于以下证据回答问题。每个结论后面必须附上引用编号 [1][2] 等。

证据：
{evidence}

问题：{question}

要求：
1. 只能基于提供的证据回答
2. 每个结论后面附上引用编号
3. 在最后列出完整的来源信息

答案：
"""
```

#### 第四步：修改返回格式
**文件：`web/backend/schemas.py`**

增强 `SourceDocument`：
```python
class SourceDocument(BaseModel):
    content: str
    source: str
    score: float
    page_num: Optional[int] = None
    chunk_index: Optional[int] = None
    doc_title: Optional[str] = None
    section_name: Optional[str] = None
```

#### 第五步：前端展示
**文件：`web/frontend/src/`**

在答案卡片旁边显示引用卡片：
```
答案：
  露天矿山开采工艺流程包括：
  1. 剥离 [1]
  2. 采矿 [2]
  3. 运输 [3]

引用：
  [1] 《采矿工程手册》p.45，第2节
  [2] 《采矿工程手册》p.48，第3节
  [3] 《采矿工程手册》p.52，第4节
```

**工作量：1-2 天**

---

### 方案 B：知识库版本管理

#### 第一步：建立知识库版本表
**新建文件：`core/kb_version_manager.py`**

```python
class KBVersionManager:
    def __init__(self):
        self.kb_versions = {}  # 或用数据库
    
    def create_version(self, kb_name, version, status="draft"):
        """创建新版本"""
        pass
    
    def publish_version(self, kb_name, version):
        """发布版本"""
        pass
    
    def rollback_version(self, kb_name, target_version):
        """回滚到某个版本"""
        pass
    
    def get_current_version(self, kb_name):
        """获取当前活跃版本"""
        pass
```

#### 第二步：修改文档入库流程
**文件：`rag_main.py` 和 `core/document_processor.py`**

改造 `main()` 函数：
```python
def main(query_mode=True, directory_path="data", kb_version="v1"):
    # 处理时指定版本
    for source_dir in conf.VALID_SOURCES:
        chunks = process_documents(
            dir_path,
            kb_version=kb_version,  # 新增
            ...
        )
```

#### 第三步：向量库增加版本字段
**文件：`core/vector_store.py`**

```python
schema.add_field(field_name="kb_version", datatype=DataType.VARCHAR, max_length=50)
schema.add_field(field_name="upload_time", datatype=DataType.VARCHAR, max_length=50)
schema.add_field(field_name="doc_status", datatype=DataType.VARCHAR, max_length=20)  # draft/published/deprecated
```

#### 第四步：增量更新机制
**新建文件：`core/incremental_update.py`**

```python
class IncrementalUpdater:
    def __init__(self, vector_store):
        self.vector_store = vector_store
        self.file_hashes = {}  # 记录文件 hash
    
    def update_documents(self, directory, kb_version):
        """增量更新：只处理新增或修改的文件"""
        for file in os.listdir(directory):
            file_hash = self._compute_hash(file)
            if file_hash not in self.file_hashes:
                # 新文件，入库
                self._add_document(file, kb_version)
            elif self.file_hashes[file] != file_hash:
                # 文件修改，替换旧版本
                self._replace_document(file, kb_version)
```

#### 第五步：后端 API
**文件：`web/backend/routers/knowledge.py`**

```python
@router.post("/versions/create")
def create_kb_version(kb_name: str, version: str):
    """创建新版本"""
    pass

@router.post("/versions/publish")
def publish_version(kb_name: str, version: str):
    """发布版本"""
    pass

@router.post("/versions/rollback")
def rollback_version(kb_name: str, target_version: str):
    """回滚版本"""
    pass

@router.get("/versions/list")
def list_versions(kb_name: str):
    """列出所有版本"""
    pass
```

**工作量：3-5 天**

---

### 方案 C：用户反馈闭环

#### 第一步：修改会话记录结构
**文件：`core/conversation_manager.py`**

在 `add_message()` 中增加反馈字段：
```python
def add_message(self, question: str, answer: str, metadata: Optional[Dict] = None, feedback: Optional[Dict] = None):
    message = {
        "question": question,
        "answer": answer,
        "timestamp": datetime.now().isoformat(),
        "metadata": metadata or {},
        "feedback": feedback or {
            "rating": None,  # 1-5 星
            "is_correct": None,  # True/False/None
            "correct_answer": None,
            "comment": None,
            "feedback_time": None,
        }
    }
    self.current_session_data["history"].append(message)
```

#### 第二步：后端反馈 API
**文件：`web/backend/routers/feedback.py`（新建）**

```python
from fastapi import APIRouter

router = APIRouter()

@router.post("/submit")
def submit_feedback(session_id: str, message_index: int, feedback: dict):
    """
    提交反馈
    feedback 包含：
    - rating: 1-5
    - is_correct: True/False
    - correct_answer: 正确答案
    - comment: 用户评论
    """
    pass

@router.get("/list")
def list_feedback(session_id: str):
    """列出某个会话的所有反馈"""
    pass

@router.get("/stats")
def feedback_stats():
    """反馈统计：满意度、错答率等"""
    pass
```

#### 第三步：修改主入口
**文件：`web/backend/main.py`**

```python
from routers import feedback

app.include_router(feedback.router, prefix="/api/feedback", tags=["反馈"])
```

#### 第四步：前端反馈按钮
**文件：`web/frontend/src/`**

在每条答案下面加：
```html
<div class="feedback-buttons">
  <button @click="submitFeedback('good')">👍 有用</button>
  <button @click="submitFeedback('bad')">👎 没用</button>
  <button @click="submitFeedback('partial')">⚠️ 部分正确</button>
  <button @click="openCorrectDialog()">✏️ 纠错</button>
</div>
```

#### 第五步：反馈统计面板
**新建文件：`web/backend/routers/metrics.py`**

```python
@router.get("/feedback-stats")
def get_feedback_stats():
    """获取反馈统计"""
    return {
        "total_questions": 100,
        "satisfied_count": 85,
        "satisfaction_rate": 0.85,
        "error_count": 15,
        "error_rate": 0.15,
        "top_errors": [...]
    }
```

**工作量：1-2 天**

---

### 方案 D：权限控制与多角色访问

#### 第一步：定义用户和角色
**新建文件���`core/auth_manager.py`**

```python
from enum import Enum
from datetime import datetime, timedelta
import jwt

class UserRole(Enum):
    ADMIN = "admin"
    REVIEWER = "reviewer"
    USER = "user"

class User:
    def __init__(self, user_id: str, username: str, role: UserRole):
        self.user_id = user_id
        self.username = username
        self.role = role

class AuthManager:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
        self.users = {}  # 或数据库
    
    def create_token(self, user_id: str) -> str:
        """生成 JWT token"""
        payload = {
            "user_id": user_id,
            "exp": datetime.utcnow() + timedelta(hours=24)
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")
    
    def verify_token(self, token: str) -> dict:
        """验证 token"""
        try:
            return jwt.decode(token, self.secret_key, algorithms=["HS256"])
        except:
            return None
```

#### 第二步：修改后端认证
**文件：`web/backend/main.py`**

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthCredentials

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthCredentials = Depends(security)):
    token = credentials.credentials
    payload = auth_manager.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload
```

#### 第三步：权限装饰器
**文件：`core/auth_manager.py`**

```python
def require_role(*roles):
    """权限装饰器"""
    def decorator(func):
        async def wrapper(current_user = Depends(get_current_user), *args, **kwargs):
            user_role = current_user.get("role")
            if user_role not in roles:
                raise HTTPException(status_code=403, detail="Permission denied")
            return await func(current_user, *args, **kwargs)
        return wrapper
    return decorator
```

#### 第四步：修改 API 端点
**文件：`web/backend/routers/knowledge.py`**

```python
@router.post("/upload")
@require_role("admin", "reviewer")
async def upload_document(current_user, file: UploadFile):
    """只有管理员和审核员可以上传"""
    pass

@router.delete("/delete/{doc_id}")
@require_role("admin")
async def delete_document(current_user, doc_id: str):
    """只有管理员可以删除"""
    pass
```

#### 第五步：审计日志
**新建文件：`core/audit_logger.py`**

```python
class AuditLogger:
    def __init__(self):
        self.logs = []
    
    def log_action(self, user_id: str, action: str, resource: str, result: str):
        """记录操作"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "action": action,
            "resource": resource,
            "result": result,
        }
        self.logs.append(log_entry)
```

#### 第六步：登录 API
**新建文件：`web/backend/routers/auth.py`**

```python
@router.post("/login")
def login(username: str, password: str):
    """用户登录"""
    # 验证用户名密码
    user = authenticate_user(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = auth_manager.create_token(user.user_id)
    return {"token": token, "user": user}

@router.post("/logout")
def logout(current_user = Depends(get_current_user)):
    """用户登出"""
    pass
```

**工作量：3-5 天**

---

## 三、优先级建议

### 如果你只有 1 周时间
**优先做这个组合：**
1. 用户反馈闭环（1-2 天）
2. 来源引用到段落/页码（1-2 天）
3. 简单的日志统计（1 天）

### 如果你有 2 周时间
**优先做这个组合：**
1. 用户反馈闭环（1-2 天）
2. 来源引用到段落/页码（1-2 天）
3. 知识库版本管理（3-5 天）
4. 简单权限控制（2-3 天）

### 如果你有 3 周以上时间
**全部做：**
1. 来源引用到段落/页码（1-2 天）
2. 知识库版本管理（3-5 天）
3. 用户反馈闭环（1-2 天）
4. 权限控制与多角色访问（3-5 天）

---

## 四、最适合毕业设计的组合

我最推荐你做这个组合（总工作量 5-7 天）：

1. **来源引用到段落/页码** ✅
   - 最容易看到效果
   - 最容易讲清楚
   - 最容易演示

2. **用户反馈闭loop** ✅
   - 最容易实现
   - 最容易展示"人机协同"
   - 最容易写论文

3. **知识库版本管理** ✅
   - 最像企业系统
   - 最容易讲"工业化"
   - 最容易答辩

这三项合起来，已经很像一个"工业级 RAG 知识平台"了。

---

## 五、下一步建议

如果你想继续，我可以帮你：

1. **直接给出代码改造方案**
   - 具体改哪些文件
   - 具体改哪些行
   - 给出代码片段

2. **帮你实现其中某一项**
   - 比如先做"来源引用"
   - 或先做"用户反馈"

3. **给出完整的实现路线图**
   - 按天数规划
   - 按优先级排序
   - 按依赖关系排序

你想要哪一个？
