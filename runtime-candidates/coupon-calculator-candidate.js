// Offline candidate only. Not loaded by the ordinary site build.
(()=>{'use strict';

 const MAX=9999999n;
 function calculate(raw,confirmed){
  const errors={};
  if(confirmed!==true)errors.scope='対象を確認できない場合は、計算せず公式の購入確認画面で確かめてください。';
  const values={};
  for(const key of ['total','discount','points']){
   const text=typeof raw?.[key]==='string'?raw[key]:'';
   if(!/^[0-9]{1,7}$/.test(text)){errors[key]='半角数字だけで、0〜9,999,999の整数を入力してください。';continue;}
   values[key]=BigInt(text);
   if(values[key]>MAX)errors[key]='9,999,999以下で入力してください。';
  }
  if(values.total===0n)errors.total='税込購入金額合計は1円以上で入力してください。';
  if(values.total!==undefined&&values.discount!==undefined&&values.discount>values.total)errors.discount='値引額は税込購入金額合計以下で入力してください。';
  if(Object.keys(errors).length)return {ok:false,errors};
  const payment=values.total-values.discount;
  const awarded=values.points*payment/values.total;
  return {ok:true,payment:payment.toString(),awarded:awarded.toString(),difference:(values.points-awarded).toString()};
 }
 const calculator=Object.freeze({calculate});


 const root=document.getElementById('datalab-coupon-calculator');
 if(!root)return;
 const get=id=>root.querySelector('[id="calc-'+id+'"]');
 const form=document.querySelector('#datalab-coupon-calculator form'),scope=get('scope'),result=get('result'),message=get('message');
 const keys=['scope','total','discount','points'];
 function clear(){result.hidden=true;message.textContent='';for(const key of keys){get(key+'-error').textContent='';get(key).removeAttribute('aria-invalid');}scope.setAttribute('aria-describedby','calc-scope-error');}
 form.addEventListener('input',()=>{const hadResult=!result.hidden;clear();if(hadResult)message.textContent='入力が変わりました。もう一度、計算してください。';});
 form.addEventListener('submit',event=>{event.preventDefault();clear();const raw={};for(const key of keys.slice(1))raw[key]=get(key).value;const value=calculator.calculate(raw,scope.checked);
  if(!value.ok){for(const [key,error]of Object.entries(value.errors)){get(key+'-error').textContent=error;get(key).setAttribute('aria-invalid','true');}message.textContent='計算できません。入力欄の案内を確認してください。';get(keys.find(key=>value.errors[key])).focus();return;}
  const format=text=>BigInt(text).toLocaleString('ja-JP');
  get('payment-result').textContent=format(value.payment)+'円';get('points-result').textContent=format(value.awarded)+'ポイント';get('difference-result').textContent=format(value.difference)+'ポイント';result.hidden=false;message.textContent='支払額'+format(value.payment)+'円、計算上の還元'+format(value.awarded)+'ポイントです。';
 });
 form.addEventListener('reset',()=>{clear();message.textContent='例の数字に戻しました。計算の対象は、もう一度確認してください。';});
 scope.setAttribute('aria-describedby','calc-scope-error');

})();
