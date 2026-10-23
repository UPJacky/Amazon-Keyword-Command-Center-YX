(function(){
  'use strict';
  const status = document.createElement('p');
  status.id = 'connection-status';
  status.setAttribute('role', 'status');
  status.className = 'notice';
  document.body.prepend(status);
  function message(text) { status.textContent = text; }
  const loginUrl = document.body.dataset.loginUrl || 'login.html';
  function recoveryLink() {
    const link = document.createElement('a');
    link.href = loginUrl;
    link.textContent = ' 返回登录';
    status.append(link);
  }
  let client;
  try {
    const config = globalThis.KWCC_PUBLIC_CONFIG;
    if (!config || typeof config !== 'object' || Array.isArray(config)
      || !['demo', 'live'].includes(config.mode))
      throw new Error('public configuration is missing or invalid');
    client = globalThis.KWCCClient.createClient({
      fetch: globalThis.fetch.bind(globalThis),
      storage: config.mode === 'live' ? sessionStorage : localStorage,
      ...globalThis.KWCC_CLIENT_OPTIONS,
      config,
    });
  } catch (_) {
    message('配置无效，已禁止登录与数据操作；不会回退到演示模式。');
    recoveryLink();
    document.querySelectorAll('main, form, .modal, .drawer').forEach(el => { el.hidden = true; });
    globalThis.KWCC = { ready: Promise.resolve(false), mode: 'blocked' };
    return;
  }
  const live = client.mode === 'live';
  const reportLifecycle = {
    invalidated: false,
    revision: 0,
    reason: null,
    invalidate(reason) {
      this.invalidated = true;
      this.revision++;
      this.reason = reason;
      globalThis.ReportUI?.invalidate?.(reason, this.revision);
    },
  };
  globalThis.KWCC = { ...client, ready: null, showError: error => message(error.message || '操作失败'), reportLifecycle };
  message(live ? '正在验证登录身份…' : 'Demo · 仅本地演示，不代表真实登录、上传或持久化保存。');
  const protectedPage=document.body.dataset.page || document.body.classList.contains('app-shell');
  const protectedContent = document.querySelector('main');
  let pageSuspended = false;
  if (!protectedPage) document.body.dataset.uiReady = 'true';
  if (protectedPage && protectedContent) protectedContent.hidden = true;
  function lock(reason) {
    if (protectedPage) reportLifecycle.invalidate('会话已结束或身份已改变，报告内容和导出已清除。请重新验证身份。');
    if (protectedPage && protectedContent) protectedContent.hidden = true;
    document.querySelectorAll('.modal, .drawer').forEach(el => { el.hidden = true; });
    message(reason);
    recoveryLink();
  }
  let authRevision = 0;
  let taskSubmitOwner = null;
  client.auth.subscribe(state => {
    authRevision++;
    if (live && ['signed_out', 'expired', 'forbidden', 'signing_in'].includes(state)) {
      taskSubmitOwner = null;
      lock(state === 'forbidden' ? '403 · 权限不足，已清除会话和数据视图；请重新登录。' : '会话已结束或过期，请重新登录。');
    }
  });
  globalThis.KWCC.ready = (async () => {
    if (!protectedPage) { message(live ? 'Live · 使用 Supabase Auth 登录。会话过期后需重新登录。' : status.textContent); return true; }
    try {
      const user = await client.auth.getUser();
      if (pageSuspended) return false;
      if (!user || (live && user.demo === true)) {
        window.location.replace(loginUrl);
        return false;
      }
      if (protectedContent) protectedContent.hidden = false;
      document.body.dataset.uiReady = 'true';
      message(live ? '已登录 · 可查看已授权店铺的任务和报告。' : status.textContent);
      return true;
    } catch (error) { lock(error.message); return false; }
  })();
  if (live && protectedPage) {
    const timer = setInterval(() => { try { client.auth.checkSession(); } catch (error) { lock(error.message); clearInterval(timer); } }, 1000);
    window.addEventListener('pagehide', () => {
      pageSuspended = true;
      clearInterval(timer);
      lock('页面已离开，返回后重新验证身份。');
    }, { once: true });
    window.addEventListener('pageshow', event => {
      if (!event.persisted) return;
      // A bfcache document contains the previous caller's DOM and in-memory
      // client. Reload creates a fresh client bound to current sessionStorage.
      pageSuspended = true;
      lock('正在重新加载并验证当前会话。');
      window.location.reload();
    });
    // Static workspace summaries and report artifacts are demo-only.
    document.querySelectorAll('.metric-grid, .content-grid, #strategy-modal').forEach(el => { el.hidden = true; });
    document.querySelectorAll('.demo-banner, .sidebar-foot, .auth-note').forEach(el => { el.textContent = 'Live · 不使用演示数据'; });
    document.querySelectorAll('#logout, a[href="login.html"]').forEach(el => { el.textContent = '退出登录'; });
  }
  const form=document.querySelector('#login-form');
  if(form && live) {
    document.querySelectorAll('.auth-note').forEach(el=>{el.textContent='Live · 会话仅保留在当前标签页，过期后需重新登录。';});
    const remember=form.querySelector('[name="remember"]');
    if(remember) {remember.checked=false;remember.disabled=true;remember.title='当前不提供长期会话或自动续期';}
  }
  if(form){form.addEventListener('submit',async function(e){
    e.preventDefault();
    const button=form.querySelector('[type="submit"]');button.disabled=true;
    const fields=new FormData(form);
    try { await client.auth.signIn(fields.get('email'), fields.get('password')); window.location.href=document.body.dataset.postLoginUrl || (loginUrl.endsWith('index.html') ? loginUrl.replace(/index\.html$/, 'workspace.html') : 'workspace.html'); }
    catch(error) { message(error.message); }
    finally { form.querySelector('[name="password"]').value=''; button.disabled=false; }
  });}
  document.querySelectorAll('#logout, a[href="login.html"]').forEach(link => link.addEventListener('click', async function(e) {
    e.preventDefault();
    if (!live) localStorage.removeItem('kwcc_demo_session');
    try { await client.auth.signOut(); window.location.href=loginUrl; }
    catch (_) { lock('本地会话已清除；服务端退出未确认，请关闭此页面或重新登录。'); }
  }));
  function toast(message){const el=document.querySelector('#toast');if(!el)return;el.textContent=message;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),2200);}
  function setModal(modal,open){if(!modal)return;modal.setAttribute('aria-hidden',String(!open));document.body.classList.toggle('modal-open',open);if(open){const first=modal.querySelector('input,select,button');if(first)first.focus();}}
  document.querySelectorAll('[data-close-modal]').forEach(el=>el.addEventListener('click',()=>setModal(el.closest('.modal'),false)));
  const task=document.querySelector('#new-task');const taskModal=document.querySelector('#new-task-modal');if(task)task.addEventListener('click',()=>setModal(taskModal,true));
  const strategy=document.querySelector('#preview-strategy');const strategyModal=document.querySelector('#strategy-modal');if(strategy)strategy.addEventListener('click',()=>setModal(strategyModal,true));
  const drawer=document.querySelector('#strategy-drawer');if(drawer){document.querySelectorAll('[data-open-drawer]').forEach(el=>el.addEventListener('click',()=>{drawer.setAttribute('aria-hidden','false');document.body.classList.add('modal-open');}));document.querySelectorAll('[data-close-drawer]').forEach(el=>el.addEventListener('click',()=>{drawer.setAttribute('aria-hidden','true');document.body.classList.remove('modal-open');}));const submit=drawer.querySelector('[data-static-submit]');if(submit)submit.addEventListener('click',()=>{const status=drawer.querySelector('[data-drawer-status]');if(status){status.hidden=false;status.textContent='演示模式：未保存配置，等待配置 API 接入。';}});}
  document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelectorAll('.modal[aria-hidden="false"]').forEach(modal=>setModal(modal,false));});
  const taskForm=document.querySelector('#new-task-form');
  if(taskForm && live) {
    taskForm.querySelector('.check-row').textContent='上传会写入我的私有输入空间，并原子登记任务和首个运行；pending 不代表 Worker 已处理或报告已生成。';
    const file=taskForm.querySelector('#report-file');
    const canUpload=Boolean(client.tasks.canUpload);
    if(file) { file.disabled=!canUpload; file.required=canUpload; }
    const submit=taskForm.querySelector('[type="submit"]');
    submit.textContent=canUpload ? '上传并创建真实任务' : '上传网关尚未配置';
    submit.disabled=!canUpload;
    const help=taskForm.querySelector('.upload-placeholder');
    help.textContent=canUpload
      ? '选择 XLSX 或 CSV。浏览器计算文件 SHA-256，网关写入私有输入桶，RPC 原子登记任务和首个 run。'
      : '需要配置应用网关后才能上传并创建真实任务；当前没有提交任何文件。';
    for (const [name, title] of [['store_id','店铺 UUID']]) {
      const label=document.createElement('label');label.textContent=title;
      const input=document.createElement('input');input.name=name;input.required=true;label.append(input);taskForm.prepend(label);
    }
    document.querySelector('#new-task-title').nextElementSibling.textContent='创建后为 pending，不代表 Worker 已处理或报告已生成。';
  }
  if(taskForm)taskForm.addEventListener('submit',async function(e){
    e.preventDefault();
    if (taskSubmitOwner) return;
    const submitOwner = Symbol('task-submit');
    taskSubmitOwner = submitOwner;
    const result=document.querySelector('#task-form-status');const button=taskForm.querySelector('[type="submit"]');button.disabled=true;
    const requestAuthRevision = authRevision;
    try {
      const data=new FormData(taskForm);
      const selected=document.querySelector('#report-file')?.files?.[0];
      const submittedSnapshot = {
        store: data.get('store_id'), asin: data.get('asin'),
        productStage: data.get('product_stage'), file: selected,
      };
      if (live) client.auth.checkSession();
      const created=await client.tasks.create({store_id:data.get('store_id'),self_asin:String(data.get('asin')).toUpperCase(),product_stage:data.get('product_stage'),file:selected});
      if (live && authRevision !== requestAuthRevision) return;
      if (live) client.auth.checkSession();
      if (live && authRevision !== requestAuthRevision) return;
      if (live && (!created || created.demo === true || created.persisted === false
        || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(created.task_id || '')
        || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(created.run_id || '')
        || !['pending','processing','completed','failed'].includes(created.status)))
        throw new Error('任务创建结果未确认；请刷新任务列表核对后再重试。');
      const runStatusLabel = {pending:'pending（尚未处理）',processing:'processing（处理中）',completed:'completed（已完成）',failed:'failed（失败）'};
      result.textContent=live ? `已确认任务 ${created.task_id} · ${runStatusLabel[created.status]}` : '演示试填完成；未保存草稿、未上传文件、未创建真实任务。';
      result.className='form-status';
      if (live) {
        const reportFile=document.querySelector('#report-file');
        const currentData = new FormData(taskForm);
        const formStillMatchesSnapshot = currentData.get('store_id') === submittedSnapshot.store
          && currentData.get('asin') === submittedSnapshot.asin
          && currentData.get('product_stage') === submittedSnapshot.productStage
          && reportFile?.files?.[0] === submittedSnapshot.file;
        if (formStillMatchesSnapshot && reportFile) reportFile.value='';
        document.querySelector('#refresh-tasks')?.click();
      }
    } catch(error) {
      if (live && authRevision !== requestAuthRevision) return;
      result.textContent=error.message;result.className='form-status';
    }
    finally {
      if (taskSubmitOwner === submitOwner) {
        taskSubmitOwner = null;
        button.disabled=false;
      }
    }
  });
  const file=document.querySelector('#report-file');if(file && !live)file.addEventListener('change',()=>{if(file.files[0])toast('演示模式不会读取或上传文件');});
  if(live && file && !client.tasks.canUpload) file.title='上传网关未配置；文件不会被读取或上传';
  document.querySelectorAll('[data-open-upload]').forEach(el=>el.addEventListener('click',()=>message(live
    ? '该页面暂不支持上传。请在工作台新建任务并选择报表文件。'
    : '演示模式不会读取或上传文件。')));
  if(live) {
    document.querySelectorAll('[data-static-submit], #preview-strategy, [data-open-drawer]').forEach(el=>{el.disabled=true;el.title='当前 RLS 未允许策略写入；未保存配置';});
    document.querySelectorAll('.policy-banner strong').forEach(el=>{el.textContent=client.strategies.canWrite ? '策略版本 · 店铺管理员可保存与回滚' : '策略只读 · 写入服务尚未配置';});
  }
})();
