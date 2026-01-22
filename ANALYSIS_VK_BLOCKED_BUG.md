# ROOT CAUSE ANALYSIS: VK BLOCKED BUG

## 🔴 MASALAH UTAMA

Bot mendeteksi VK account blocked (Error 5) tapi MASIH mengeksekusi task VK lainnya,
menyebabkan task non-VK ikut terskip.

---

## 🔍 ROOT CAUSE

### 1. **RACE CONDITION antara `task_type_skip` dan `vk_account_blocked`**

**Lokasi:** `automation_core.py` line 3687-3692

```python
if 'Error 5' in error_str and 'user is blocked' in error_str:
    self.vk_account_blocked = True
    print(f"  {R}⚠ VK Account is BLOCKED - skipping all VK tasks{W}")
    
    vk_task_types = ['friends', 'likes', 'repost', 'group', 'poll', 'video']
    for vk_task in vk_task_types:
        self.task_type_skip.add(vk_task)  # ❌ MASALAH DI SINI
```

**PROBLEM:**
- `task_type_skip` adalah mekanisme GENERIC untuk skip task dengan consecutive errors
- Ketika VK blocked, bot menambahkan SEMUA VK task types ke `task_type_skip`
- Tapi `task_type_skip` juga digunakan untuk task NON-VK (IG, TG, dll)
- Ini menyebabkan SHARED STATE yang membingungkan

### 2. **DOUBLE FILTERING yang TIDAK KONSISTEN**

**Lokasi:** `auto_process_all_tasks()` line 4010-4090

Ada 2 tempat filtering VK tasks:

**Filter #1** (line 4050-4053):
```python
vk_task_types = ['friends', 'group', 'likes', 'repost', 'poll', 'video']
if v in vk_task_types and (self.vk_account_blocked or not vk_api_available):
    continue  # ✅ BENAR - skip VK tasks
```

**Filter #2** (line 4090-4093):
```python
vk_task_types = ['friends', 'group', 'likes', 'repost', 'poll', 'video']
if v in vk_task_types and self.vk_account_blocked:
    print(f"  {Y}Skipping VK {v} - account blocked{W}")
    continue  # ✅ BENAR - skip VK tasks
```

**PROBLEM:**
- Ada DUPLICATE logic di 2 tempat berbeda
- Tapi task sudah masuk ke `enabled` list sebelum filter #2
- Filter #1 dan #2 TIDAK sinkron dengan `task_type_skip`

### 3. **TASK SUDAH DI-FETCH sebelum filtering**

**Lokasi:** `auto_process_all_tasks()` line 4100-4110

```python
for t in enabled:
    tasks = self.get_tasks(t)  # ❌ FETCH dari server DULU
    
    if tasks is None:
        skipped_types.append(t)
        continue
```

**PROBLEM:**
- Bot FETCH tasks dari server SEBELUM cek `vk_account_blocked`
- Jika server kirim VK tasks, bot sudah ambil dan masukkan ke queue
- Filtering terjadi SETELAH tasks sudah di-fetch

### 4. **INCONSISTENT RETURN VALUES di `process()`**

**Lokasi:** `process()` line 3820-3900

```python
def process(self, task):
    # ...
    h = self.begin(aid)
    if h == "SKIP":
        return None  # ❌ Return None
    if h == "VK_ACCOUNT_BLOCKED":
        return None  # ❌ Return None juga
```

**PROBLEM:**
- `begin()` return "VK_ACCOUNT_BLOCKED" (line 3538)
- Tapi `process()` treat ini sama dengan "SKIP" (return None)
- Tidak ada propagasi error ke level atas
- Task counter tetap jalan seolah task berhasil di-skip

---

## 📊 FLOW EKSEKUSI SAAT INI

```
1. auto_process_all_tasks() dipanggil
   ↓
2. Build enabled[] list (filter #1 - check vk_account_blocked)
   ↓
3. Loop enabled[] → get_tasks(t) untuk SETIAP type
   ↓ (❌ VK tasks sudah di-fetch dari server)
   ↓
4. Loop all_tasks[] → process(task)
   ↓
5. process() → begin(aid)
   ↓
6. begin() detect VK Error 5
   ↓
7. Set vk_account_blocked = True
   ↓
8. Add VK types ke task_type_skip
   ↓
9. Return "VK_ACCOUNT_BLOCKED"
   ↓
10. process() return None
    ↓
11. Main loop treat None sebagai "skip"
    ↓
12. ❌ TAPI task VK berikutnya SUDAH di-fetch
    ↓
13. ❌ Loop continue, VK tasks tetap diproses
```

**KENAPA BUG TERJADI:**
- VK blocked detection terjadi di TENGAH execution (step 6-8)
- Tasks sudah di-fetch SEBELUM detection (step 3)
- Filtering di step 2 TIDAK efektif karena flag belum set
- Task queue sudah penuh dengan VK tasks yang akan diproses

---

## 🛠️ REKOMENDASI PERBAIKAN

### SOLUSI 1: **Separate VK Blocked Flag + Early Exit**

```python
class VKSerfingBot:
    def __init__(self, ...):
        # Separate flags untuk setiap platform
        self.vk_account_blocked = False
        self.vk_captcha_required = False
        self.ig_otp_required = False
        self.tg_flood_wait_until = 0
        
        # Task type skip untuk GENERIC errors (bukan platform-specific)
        self.task_type_skip = set()
        self.task_type_errors = {}
    
    def _is_task_allowed(self, task_type):
        """
        Centralized task filtering logic
        Returns: (allowed: bool, reason: str)
        """
        # Check platform-specific blocks
        vk_tasks = ['friends', 'group', 'likes', 'repost', 'poll', 'video']
        ig_tasks = ['instagram_followers', 'instagram_likes', 'instagram_comments']
        tg_tasks = ['telegram_followers', 'telegram_views']
        
        if task_type in vk_tasks:
            if self.vk_account_blocked:
                return False, "VK account blocked"
            if self.vk_captcha_required:
                return False, "VK captcha required"
            if not hasattr(self, 'vk') or self.vk is None:
                return False, "VK API not configured"
        
        if task_type in ig_tasks:
            if self.ig and self.ig.otp_required:
                return False, "IG OTP required"
        
        if task_type in tg_tasks:
            if time.time() < self.tg_flood_wait_until:
                return False, "TG flood wait"
        
        # Check generic task type skip (consecutive errors)
        if task_type in self.task_type_skip:
            return False, f"Too many errors ({self.task_type_errors.get(task_type, 0)})"
        
        return True, ""
    
    def auto_process_all_tasks(self, max_tasks=None):
        """
        Main task processing loop with proper filtering
        """
        # Build enabled task types
        enabled = []
        for config_key, task_type in self.task_type_mapping.items():
            if not self.config.get('task_types', {}).get(config_key):
                continue
            
            # ✅ FILTER EARLY - before fetching tasks
            allowed, reason = self._is_task_allowed(task_type)
            if not allowed:
                print(f"  {Y}Skipping {task_type}: {reason}{W}")
                continue
            
            enabled.append(task_type)
        
        # Fetch tasks ONLY for enabled types
        all_tasks = []
        for task_type in enabled:
            if STOP_FLAG:
                break
            
            # ✅ RE-CHECK before fetch (in case flag changed)
            allowed, reason = self._is_task_allowed(task_type)
            if not allowed:
                print(f"  {Y}Skipping {task_type}: {reason}{W}")
                continue
            
            tasks = self.get_tasks(task_type)
            if tasks:
                all_tasks.extend(tasks)
        
        # Process tasks
        for task in all_tasks:
            if STOP_FLAG:
                break
            
            task_type = task.get('type', '')
            
            # ✅ FINAL CHECK before processing
            allowed, reason = self._is_task_allowed(task_type)
            if not allowed:
                print(f"  {Y}Skip {task_type}: {reason}{W}")
                continue
            
            result = self.process(task)
            
            # Handle result
            if result is True:
                # Success - reset error counter for this type
                self.task_type_errors[task_type] = 0
                if task_type in self.task_type_skip:
                    self.task_type_skip.remove(task_type)
            elif result is False:
                # Failure - increment error counter
                self.task_type_errors[task_type] = self.task_type_errors.get(task_type, 0) + 1
                if self.task_type_errors[task_type] >= 3:
                    self.task_type_skip.add(task_type)
```

### SOLUSI 2: **Clean Error Handling di VK Methods**

```python
def _handle_vk_error(self, error, task_type):
    """
    Centralized VK error handling
    Returns: action to take ('skip', 'retry', 'block')
    """
    error_str = str(error)
    
    # Error 5: User blocked
    if 'Error 5' in error_str and 'user is blocked' in error_str:
        if not self.vk_account_blocked:
            self.vk_account_blocked = True
            print(f"\n{R}═══ VK ACCOUNT BLOCKED ═══{W}")
            print(f"{R}All VK tasks will be skipped{W}\n")
        return 'block'
    
    # Error 14: Captcha
    if 'Error 14' in error_str or 'Captcha' in error_str:
        if not self.vk_captcha_required:
            self.vk_captcha_required = True
            print(f"\n{Y}═══ VK CAPTCHA REQUIRED ═══{W}")
            print(f"{Y}All VK tasks will be skipped this cycle{W}\n")
        return 'block'
    
    # Error 6: Too fast / Flood
    if 'Error 6' in error_str or 'Too many requests' in error_str:
        self.vk_flood_control_until = time.time() + 300  # 5 min
        print(f"{Y}VK Flood control - 5 min cooldown{W}")
        return 'skip'
    
    # Other errors - let task_type_skip handle it
    return 'retry'

def begin(self, aid):
    """
    Begin task - with proper error handling
    """
    # Early exit if VK blocked
    if self.vk_account_blocked:
        return "VK_BLOCKED"
    
    if not self.vk:
        return "VK_NOT_CONFIGURED"
    
    try:
        # ... VK API calls ...
        return True
    
    except Exception as e:
        action = self._handle_vk_error(e, 'vk')
        
        if action == 'block':
            return "VK_BLOCKED"
        elif action == 'skip':
            return "VK_SKIP"
        else:
            raise  # Let upper layer handle
```

### SOLUSI 3: **Task Type Categorization**

```python
class TaskCategory:
    VK = ['friends', 'group', 'likes', 'repost', 'poll', 'video']
    IG_ACTION = ['instagram_followers', 'instagram_likes', 'instagram_comments']
    IG_VIEW = ['instagram_video', 'instagram_views', 'instagram_story']
    TG = ['telegram_followers', 'telegram_views']
    TIKTOK = ['tiktok_video']
    
    @classmethod
    def get_category(cls, task_type):
        if task_type in cls.VK:
            return 'vk'
        if task_type in cls.IG_ACTION:
            return 'ig_action'
        if task_type in cls.IG_VIEW:
            return 'ig_view'
        if task_type in cls.TG:
            return 'telegram'
        if task_type in cls.TIKTOK:
            return 'tiktok'
        return 'unknown'

# Usage:
def _is_task_allowed(self, task_type):
    category = TaskCategory.get_category(task_type)
    
    if category == 'vk':
        if self.vk_account_blocked:
            return False, "VK blocked"
        if not self.vk:
            return False, "VK not configured"
    
    elif category == 'ig_action':
        if self.ig and self.ig.otp_required:
            return False, "IG OTP required"
    
    # ... etc
    
    return True, ""
```

---

## 🎯 IMPLEMENTASI MINIMAL (Quick Fix)

Jika ingin fix cepat tanpa refactor besar:

```python
# Di auto_process_all_tasks(), SEBELUM loop all_tasks:

# ✅ Filter out VK tasks if blocked
if self.vk_account_blocked:
    vk_task_types = ['friends', 'group', 'likes', 'repost', 'poll', 'video']
    all_tasks = [t for t in all_tasks if t.get('type') not in vk_task_types]
    print(f"  {R}Filtered out {len([t for t in all_tasks if t.get('type') in vk_task_types])} VK tasks (account blocked){W}")

# ✅ Filter out IG action tasks if OTP required
if self.ig and self.ig.otp_required:
    ig_action_types = ['instagram_followers', 'instagram_likes', 'instagram_comments']
    all_tasks = [t for t in all_tasks if t.get('type') not in ig_action_types]
```

---

## 📝 KESIMPULAN

**Root Cause:**
1. VK blocked detection terjadi SETELAH tasks di-fetch
2. `task_type_skip` digunakan untuk SEMUA error types (VK, IG, TG) → shared state
3. Double filtering yang tidak konsisten
4. Tidak ada early exit mechanism

**Fix Strategy:**
1. Separate platform-specific flags dari generic error flags
2. Centralized filtering logic (`_is_task_allowed()`)
3. Filter BEFORE fetch, RE-CHECK before process
4. Clean error propagation dengan meaningful return values

**Priority:**
- HIGH: Implement `_is_task_allowed()` + filter before fetch
- MEDIUM: Clean up `task_type_skip` logic
- LOW: Refactor error handling dengan TaskCategory

