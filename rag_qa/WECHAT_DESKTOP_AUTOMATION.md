# WeChat Desktop Automation

This workflow is the Windows desktop capture path for WeChat article collection.

It is intended for the case where:

1. direct HTTP crawling is blocked by WeChat verification or risk control
2. the operator already keeps the Windows desktop WeChat client logged in
3. article collection should stay fully inside the desktop client workflow

## Goal

Use the logged-in PC WeChat client as the trusted execution environment, then:

1. search for the public account in the desktop client
2. enter the history page inside the client
3. open an article by title fragment
4. capture screenshots and window text while auto paging down
5. import the package into the existing EduRAG article artifact layout

## Dependencies

- Windows desktop WeChat client
- logged-in WeChat session on the same workstation
- pywinauto
- pillow

Install desktop automation dependency in the EduRAG virtual environment:

```powershell
cd rag_qa
.venv\Scripts\python.exe -m pip install pywinauto==0.6.9
```

## Script

Main script:

- capture_wechat_desktop.py

Output root:

- data/wechat_collector/desktop_capture

Remembered profile store:

- data/wechat_collector/desktop_capture/device_profiles.json

## Remembered Profiles

Recommended isolation key:

- operator_id + machine_name + account_id

Profile naming format:

- operator_id__machine_name__account_id

Example:

- zhangsan__office_pc__my_wechat_account

## Basic CLI Example

```powershell
cd rag_qa
.venv\Scripts\python.exe capture_wechat_desktop.py \
  --operator-id zhangsan \
  --account-id my_wechat_account \
  --search-query "矿业工程学院" \
  --article-title "毕业典礼" \
  --steps 6 \
  --auto-scroll \
  --json-output
```

If WeChat is not already running, provide WeChat.exe explicitly:

```powershell
cd rag_qa
.venv\Scripts\python.exe capture_wechat_desktop.py \
  --operator-id zhangsan \
  --account-id my_wechat_account \
  --wechat-path "C:/Program Files/Tencent/WeChat/WeChat.exe" \
  --search-query "矿业工程学院" \
  --article-title "毕业典礼" \
  --steps 6 \
  --auto-scroll
```

If the article window is already open, skip the history-navigation step:

```powershell
cd rag_qa
.venv\Scripts\python.exe capture_wechat_desktop.py \
  --operator-id zhangsan \
  --account-id my_wechat_account \
  --profile zhangsan__office_pc__my_wechat_account \
  --skip-history \
  --steps 6 \
  --auto-scroll
```

## Frontend Workflow

The WeChat annotator page now includes a desktop capture panel where you can:

1. enter operator_id
2. select an existing desktop profile
3. fill search query and article title fragment
4. optionally specify WeChat.exe and custom window title regex
5. start desktop automation and stream progress in real time
6. optionally import, clean, and ingest immediately

## Package Format

The desktop script writes the same manifest-based package structure used by the
Android capture workflow. The only difference is:

- capture_type = windows_wechat_desktop

It still writes:

1. manifest.json
2. screenshots/step_xx.png
3. ui_dumps/step_xx.txt

The existing importer merges UI text and OCR text from screenshots, so no new
importer is required.

## Current Scope

The first desktop MVP automates these stages:

1. connect to an existing WeChat desktop window
2. fill the visible search box
3. try to click a history entry such as "历史消息" or "全部消息"
4. try to click an article by title fragment
5. capture screenshots and page down automatically

Known limitations of the first version:

1. it depends on the current desktop WeChat UI hierarchy and visible labels
2. different WeChat versions may expose slightly different controls
3. if the history entry text differs, you may need to open the public account conversation manually and use --skip-history

## Import Step

Import still uses the existing importer:

```powershell
cd rag_qa
.venv\Scripts\python.exe import_wechat_mobile_package.py \
  --package "data/wechat_collector/desktop_capture/my_wechat_account_20260422_120000" \
  --clean \
  --ingest
```