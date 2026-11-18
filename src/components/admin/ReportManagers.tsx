'use client';

import { FormEvent, useMemo, useState } from 'react';

type Item = { id:string; category:string; title:string; body:string; status:string; priority:string; pinned:boolean; confirmed:boolean; structuredData?:Record<string,string>; updatedAt:string };
type Field = { id:string; label:string; choices:string[]; required:boolean };
type Settings = { operationOptions?: { title?:string; footer?:string; fields?:Field[] } } | null;
type Api = (url:string, options?:RequestInit)=>Promise<unknown>;
type Props = { items:Item[]; settings:Settings; busy:boolean; action:(fn:()=>Promise<unknown>, message:string)=>Promise<void>; api:Api };

function Box({children,className=''}:{children:React.ReactNode;className?:string}) { return <div className={`rounded-xl border border-zinc-800 bg-black p-4 sm:p-5 ${className}`}>{children}</div>; }

export function CentralReportsManager({items,settings,busy,action,api}:Props) {
  const fields = useMemo<Field[]>(()=>settings?.operationOptions?.fields || [],[settings?.operationOptions?.fields]);
  const [values,setValues]=useState<Record<string,string>>({});
  const ready=fields.every(field=>!field.required||values[field.id]);
  const preview=useMemo(()=>[
    settings?.operationOptions?.title||'بلاغ العمليات المركزية',
    `الوقت والتاريخ: ${new Date().toLocaleString('ar-SY')}`,
    ...fields.filter(field=>values[field.id]).map(field=>`${field.label}: ${values[field.id]}`),
    settings?.operationOptions?.footer?'':null,
    settings?.operationOptions?.footer||null,
  ].filter(value=>value!==null).join('\n'),[fields,settings?.operationOptions?.footer,settings?.operationOptions?.title,values]);
  async function submit(e:FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const submitter=(e.nativeEvent as SubmitEvent).submitter as HTMLButtonElement|null;
    const fd=new FormData(e.currentTarget);
    await action(()=>api('/api/admin/operations/reports',{method:'POST',body:JSON.stringify({
      values, status:submitter?.value==='draft'?'draft':'published', priority:fd.get('priority'), pinned:fd.get('pinned')==='on',
    })}),submitter?.value==='draft'?'تم حفظ مسودة البلاغ':'تم نشر البلاغ المركزي');
    setValues({}); e.currentTarget.reset();
  }
  const reports=items.filter(item=>item.category==='central-operations');
  return <><div className="mb-4"><h2 className="text-xl font-bold">إضافة بلاغ للعمليات المركزية</h2><p className="mt-1 text-sm text-zinc-500">اختر القيم عبر الأزرار؛ يضاف الوقت والتاريخ والفوتر تلقائياً.</p></div>
    <div className="grid gap-4 xl:grid-cols-[1.35fr_.65fr]"><Box><form onSubmit={submit} className="space-y-5">{fields.map(field=><fieldset key={field.id}><legend className="mb-2 text-sm font-bold text-amber-200">{field.label}{field.required&&<span className="mr-1 text-red-400">*</span>}</legend><div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">{field.choices.map(choice=><button type="button" key={choice} onClick={()=>setValues(current=>({...current,[field.id]:choice}))} className={`min-h-12 rounded-lg border px-3 py-2 text-sm transition ${values[field.id]===choice?'border-amber-300 bg-amber-300 font-bold text-black':'border-zinc-700 bg-zinc-950 text-zinc-300 hover:border-amber-500'}`}>{choice}</button>)}</div></fieldset>)}{!fields.length&&<p className="rounded border border-red-900 bg-red-950/30 p-3 text-sm text-red-300">أضف حقول البلاغ من إعدادات العمليات أولاً.</p>}<div className="grid gap-3 sm:grid-cols-2"><select name="priority" className="field"><option value="normal">أولوية اعتيادية</option><option value="important">مهم</option><option value="urgent">عاجل</option><option value="critical">حرج</option></select><label className="flex items-center gap-2 rounded-lg border border-zinc-800 px-3 text-sm"><input name="pinned" type="checkbox"/> تثبيت البلاغ بالأعلى</label></div><div className="flex flex-col gap-2 sm:flex-row"><button disabled={busy||!ready||!fields.length} value="published" className="btn-primary flex-1">نشر البلاغ الآن</button><button disabled={busy||!ready||!fields.length} value="draft" className="btn-secondary flex-1">حفظ كمسودة</button></div></form></Box><Box><h3 className="mb-3 font-bold text-zinc-300">معاينة مباشرة</h3><pre className="whitespace-pre-wrap text-sm leading-7 text-zinc-400">{preview}</pre></Box></div>
    <ReportList title="سجل البلاغات المركزية" reports={reports} busy={busy} action={action} api={api}/></>;
}

export function IntelligenceReportsManager({items,busy,action,api}:Props) {
  const [edit,setEdit]=useState<Item|null>(null);
  async function submit(e:FormEvent<HTMLFormElement>) {
    e.preventDefault(); const fd=new FormData(e.currentTarget); const submitter=(e.nativeEvent as SubmitEvent).submitter as HTMLButtonElement|null;
    const status=submitter?.value==='draft'?'draft':'published';
    const body={title:fd.get('title'),body:fd.get('body'),priority:fd.get('priority'),pinned:fd.get('pinned')==='on',confirmed:fd.get('confirmed')==='on',status};
    await action(()=>api(edit?`/api/admin/content/${edit.id}`:'/api/admin/intelligence/reports',{method:edit?'PATCH':'POST',body:JSON.stringify(body)}),edit?'تم تحديث البلاغ المعلوماتي':status==='draft'?'تم حفظ المسودة':'تم نشر البلاغ المعلوماتي');
    setEdit(null); e.currentTarget.reset();
  }
  const reports=items.filter(item=>item.category==='intelligence-reports');
  return <><div className="mb-4"><h2 className="text-xl font-bold">إضافة بلاغ معلوماتي</h2><p className="mt-1 text-sm text-zinc-500">محرر مستقل لنشر البلاغ كاملاً كخبر بعنوان واحد.</p></div><Box><form onSubmit={submit} className="space-y-3"><input key={`${edit?.id}-title`} name="title" defaultValue={edit?.title||''} className="field text-base font-bold" placeholder="عنوان البلاغ المعلوماتي" maxLength={240} required/><textarea key={`${edit?.id}-body`} name="body" defaultValue={edit?.body||''} className="field min-h-56 leading-7" placeholder="اكتب نص الخبر أو البلاغ كاملاً..." maxLength={20000} required/><div className="grid gap-3 sm:grid-cols-2"><select key={`${edit?.id}-priority`} name="priority" defaultValue={edit?.priority||'normal'} className="field"><option value="normal">اعتيادي</option><option value="important">مهم</option><option value="urgent">عاجل</option><option value="critical">حرج</option></select><div className="space-y-2 rounded-lg border border-zinc-800 p-3 text-sm"><label className="flex items-center gap-2"><input name="confirmed" type="checkbox" defaultChecked={edit?.confirmed}/> أؤكد صحة البلاغ</label><label className="flex items-center gap-2"><input name="pinned" type="checkbox" defaultChecked={edit?.pinned}/> تثبيت بالأعلى</label></div></div><div className="flex flex-col gap-2 sm:flex-row"><button disabled={busy} value="published" className="btn-primary flex-1">{edit?'حفظ ونشر':'نشر البلاغ'}</button><button disabled={busy} value="draft" className="btn-secondary flex-1">حفظ كمسودة</button>{edit&&<button type="button" onClick={()=>setEdit(null)} className="btn-secondary">إلغاء التعديل</button>}</div></form></Box><ReportList title="سجل البلاغات المعلوماتية" reports={reports} busy={busy} action={action} api={api} onEdit={setEdit}/></>;
}

function ReportList({title,reports,busy,action,api,onEdit}:{title:string;reports:Item[];busy:boolean;action:Props['action'];api:Props['api'];onEdit?:(item:Item)=>void}) {
  return <div className="mt-5"><h3 className="mb-3 font-bold">{title} <span className="text-sm text-zinc-600">({reports.length})</span></h3><div className="space-y-2">{reports.map(item=><Box key={item.id} className="!p-4"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div className="min-w-0"><div className="flex flex-wrap gap-2 text-[11px]"><span className="tag">{item.status==='published'?'منشور':item.status==='draft'?'مسودة':'مؤرشف'}</span><span className={item.priority==='critical'?'text-red-400':'text-zinc-500'}>{item.priority}</span><span className="text-zinc-600">{new Date(item.updatedAt).toLocaleString('ar-SY')}</span></div><h4 className="mt-2 font-bold">{item.title}</h4><p className="mt-2 line-clamp-4 whitespace-pre-line text-sm leading-6 text-zinc-500">{item.body}</p></div><div className="flex shrink-0 flex-wrap gap-2">{onEdit&&<button disabled={busy} onClick={()=>onEdit(item)} className="btn-secondary">تعديل</button>}{item.category==='central-operations'&&item.status==='draft'&&<button disabled={busy} onClick={()=>action(()=>api(`/api/admin/content/${item.id}`,{method:'PATCH',body:JSON.stringify({status:'published'})}),'تم نشر المسودة')} className="btn-primary">نشر</button>}<button disabled={busy} onClick={()=>confirm('حذف هذا البلاغ؟')&&action(()=>api(`/api/admin/content/${item.id}`,{method:'DELETE'}),'تم حذف البلاغ')} className="rounded border border-red-800 px-3 py-2 text-sm text-red-300">حذف</button></div></div></Box>)}{!reports.length&&<p className="rounded-xl border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-600">لا توجد بلاغات بعد</p>}</div></div>;
}
