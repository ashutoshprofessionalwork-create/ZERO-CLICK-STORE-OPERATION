const customer="demo-user";

function say(text, cls){
 const d=document.createElement("div");
 d.className="msg "+cls;
 d.innerHTML=text;
 document.getElementById("chat").appendChild(d);
 d.scrollIntoView();
}

async function send(){
 const input=document.getElementById("msg");
 const message=input.value.trim();
 if(!message)return;
 say("You: "+message,"user");
 input.value="";

 const r=await fetch("/api/chat",{
   method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify({customer_id:customer,message})
 });
 const x=await r.json();
 let html="Bot: "+x.reply;

 if(x.cart){
   html+="<br><br><b>Cart:</b>";
   x.cart.items.forEach(i=>{
     html+=`<br>${i.product} — ${i.quantity} ${i.unit} — ₹${i.line_total}`;
   });
   html+=`<br><br>Subtotal: ₹${x.cart.subtotal}`;
   html+=`<br>Delivery: ₹${x.cart.delivery}`;
   html+=`<br><b>Total: ₹${x.cart.total}</b>`;
 }
 say(html,"bot");
 loadProducts();
 orders();
}

async function loadProducts(){
 const r=await fetch("/api/products");
 const p=await r.json();
 document.getElementById("products").innerHTML=p.map(x=>
 `<div class="product"><b>${x.name}</b><br>₹${x.price}/${x.unit}<br>Stock: ${x.stock} ${x.unit}</div>`
 ).join("");
}

async function orders(){
 const r=await fetch("/api/orders");
 const x=await r.json();
 document.getElementById("orders").innerHTML=x.length
 ? x.map(o=>`<div class="order"><b>${o.order_id}</b> — ${o.status}<br>Customer: ${o.customer_id}<br>Total: ₹${o.total}</div>`).join("")
 : "<p>No confirmed orders.</p>";
}

document.getElementById("msg").addEventListener("keydown",e=>{
 if(e.key==="Enter")send();
});

loadProducts();
orders();
say("Bot: Tell me what groceries you need. I will not change store inventory until you explicitly confirm the final order.","bot");
