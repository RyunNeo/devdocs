import { test, expect, type Page } from "@playwright/test";

async function prepare(page: Page) {
  const registered=await page.request.post('/api/auth/register',{data:{email:`experience-${Date.now()}-${Math.random()}@example.com`,password:'Study-safe-2026!'}});
  expect(registered.status()).toBe(201);
  const kb=await (await page.request.post('/api/knowledge-bases',{data:{name:'会话体验'}})).json();
  const doc=await (await page.request.post(`/api/knowledge-bases/${kb.id}/documents`,{multipart:{file:{name:'react.md',mimeType:'text/markdown',buffer:Buffer.from('# React\n\n组件使用状态。')}}})).json();
  expect((await page.request.post(`/api/documents/${doc.id}/index`)).status()).toBe(200);
  await page.goto(`/knowledge-bases/${kb.id}/chat`);
  await expect(page.getByRole('heading',{name:'会话体验'})).toBeVisible();
  return kb.id as string;
}

test('Enter sends, Shift Enter and IME confirmation do not send',async({page})=>{
  await prepare(page);
  const input=page.getByLabel('问题',{exact:true});
  await input.fill('第一行');
  await input.press('Shift+Enter');
  await input.press('x');
  await expect(input).toHaveValue('第一行\nx');
  let requests=0;
  page.on('request',request=>{if(request.url().endsWith('/chat/stream')) requests++;});
  await input.dispatchEvent('keydown',{key:'Enter',code:'Enter',isComposing:true,keyCode:229});
  await input.dispatchEvent('keydown',{key:'Enter',code:'Enter',repeat:true});
  expect(requests).toBe(0);
  await input.press('Enter');
  await expect(page.getByText('回答完成',{exact:true})).toBeVisible();
  expect(requests).toBe(1);
});

test('unvalidated draft stays hidden, only normalized final answer is displayed',async({page})=>{
  await prepare(page);
  await page.getByLabel('问题',{exact:true}).fill('拒答测试');
  await page.getByRole('button',{name:'发送问题',exact:true}).click();
  await expect(page.getByText('正在生成',{exact:true})).toBeVisible();
  await expect(page.getByText('不应展示的推测正文',{exact:false})).toHaveCount(0);
  await expect(page.getByText('回答完成',{exact:true})).toBeVisible();
  await expect(page.locator('.chat-body').last()).toContainText('未找到足够依据');
  await expect(page.getByText('INSUFFICIENT_EVIDENCE',{exact:false})).toHaveCount(0);
});

test('history restores same conversation and explicit new stays new on refresh',async({page})=>{
  const kb=await prepare(page);
  await page.getByLabel('问题',{exact:true}).fill('解释组件状态');
  await page.getByRole('button',{name:'发送问题',exact:true}).click();
  await expect(page.getByText('回答完成',{exact:true})).toBeVisible();
  const id=new URL(page.url()).searchParams.get('conversation');
  await page.getByRole('link',{name:'历史会话',exact:true}).click();
  await page.getByRole('link',{name:'解释组件状态',exact:true}).click();
  await expect(page).toHaveURL(new RegExp(`conversation=${id}`));
  await expect(page.getByText('回答完成',{exact:true})).toBeVisible();
  await page.getByLabel('问题',{exact:true}).fill('再解释一下');
  await page.getByLabel('问题',{exact:true}).press('Enter');
  await expect(page.getByText('回答完成',{exact:true})).toHaveCount(2);
  await page.goto(`/knowledge-bases/${kb}/chat`);
  await expect(page.getByText('回答完成',{exact:true})).toHaveCount(2);
  expect(new URL(page.url()).searchParams.get('conversation')).toBe(id);
  await page.getByRole('button',{name:'新会话',exact:true}).click();
  await expect(page).toHaveURL(/new=1/);
  await page.reload();
  await expect(page.getByText('暂无消息',{exact:true})).toBeVisible();
  const history=await (await page.request.get(`/api/knowledge-bases/${kb}/conversations`)).json();
  expect(history.total).toBe(1);
  await page.getByLabel('问题',{exact:true}).fill('新的独立问题');
  await page.getByLabel('问题',{exact:true}).press('Enter');
  await expect(page.getByText('回答完成',{exact:true})).toHaveCount(1);
  expect(new URL(page.url()).searchParams.get('conversation')).not.toBe(id);
  expect((await (await page.request.get(`/api/knowledge-bases/${kb}/conversations`)).json()).total).toBe(2);
  await page.getByRole('link',{name:'历史会话',exact:true}).click();
  await expect(page.getByRole('link',{name:'新的独立问题',exact:true})).toBeVisible();
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({path:'../../work/stage5-history-mobile.png',fullPage:true});
  await page.setViewportSize({width:1440,height:900});
  await page.screenshot({path:'../../work/stage5-history-desktop.png',fullPage:true});
});

test('older messages are prepended without duplicates',async({page})=>{
  const kb=await prepare(page);
  const id=(await (await page.request.post(`/api/knowledge-bases/${kb}/conversations`,{data:{}})).json()).id;
  await page.route(`**/api/conversations/${id}*`,async route=>{
    const before=Number(new URL(route.request().url()).searchParams.get('before_sequence') ?? 85);
    const start=Math.max(1,before-40);
    const messages=Array.from({length:before-start},(_,i)=>({id:`history-${start+i}`,sequence:start+i,role:'user',status:'completed',content:`旧消息 ${start+i}`,run_id:null,citations:[],error_code:null}));
    await route.fulfill({json:{id,knowledge_base_id:kb,messages,has_older:start>1}});
  });
  await page.goto(`/knowledge-bases/${kb}/chat?conversation=${id}`);
  await expect(page.locator('.chat-message')).toHaveCount(40);
  await page.getByRole('button',{name:'加载更早消息',exact:true}).click();
  await expect(page.locator('.chat-message')).toHaveCount(80);
  await page.getByRole('button',{name:'加载更早消息',exact:true}).click();
  await expect(page.locator('.chat-message')).toHaveCount(84);
  await expect(page.getByRole('button',{name:'加载更早消息',exact:true})).toHaveCount(0);
  await expect(page.locator('.chat-message').first()).toContainText('旧消息 1');
});

test('late recent-conversation response cannot replace explicit new page',async({page})=>{
  const kb=await prepare(page);
  const id=(await (await page.request.post(`/api/knowledge-bases/${kb}/conversations`,{data:{}})).json()).id;
  let release!:()=>void;
  const gate=new Promise<void>(resolve=>{release=resolve;});
  await page.route(`**/api/knowledge-bases/${kb}/conversations?limit=1*`,async route=>{
    await gate;
    await route.fulfill({json:{items:[{id}],total:1,limit:1,offset:0}}).catch(()=>{});
  });
  try {
    const request=page.waitForRequest(r=>r.url().includes('/conversations?limit=1'));
    await page.goto(`/knowledge-bases/${kb}/chat`);
    await request;
    await page.goto(`/knowledge-bases/${kb}/chat?new=1`);
    await expect(page.getByText('暂无消息',{exact:true})).toBeVisible();
    release();
    await expect(page).toHaveURL(/new=1/);
    await expect(page.getByText('暂无消息',{exact:true})).toBeVisible();
  } finally { release(); }
});

test('return navigation is disabled during generation',async({page})=>{
  await prepare(page);
  await page.getByLabel('问题',{exact:true}).fill('慢一点说明');
  await page.getByLabel('问题',{exact:true}).press('Enter');
  await expect(page.getByText('正在生成',{exact:true})).toBeVisible();
  await expect(page.locator('.knowledge-base-header').getByRole('link',{name:'知识库',exact:true})).toHaveAttribute('aria-disabled','true');
  await expect(page.getByRole('link',{name:'文档',exact:true})).toHaveAttribute('aria-disabled','true');
  await page.getByRole('button',{name:'停止生成',exact:true}).click();
});

test('another tab refreshes completed earlier answer before followup',async({page})=>{
  const kb=await prepare(page);
  await page.getByLabel('问题',{exact:true}).fill('慢一点说明');
  await page.getByLabel('问题',{exact:true}).press('Enter');
  await expect(page.getByText('正在生成',{exact:true})).toBeVisible();
  const id=new URL(page.url()).searchParams.get('conversation');
  const other=await page.context().newPage();
  try {
    await other.goto(`/knowledge-bases/${kb}/chat?conversation=${id}`);
    await expect(other.locator('.chat-message')).toHaveCount(2);
    await expect(page.getByText('回答完成',{exact:true})).toBeVisible({timeout:15000});
    await other.getByLabel('问题',{exact:true}).fill('继续解释');
    await other.getByLabel('问题',{exact:true}).press('Enter');
    await expect(other.getByText('回答完成',{exact:true})).toHaveCount(2);
    await expect(other.getByText('正在生成',{exact:true})).toHaveCount(0);
  } finally { await other.close(); }
});
