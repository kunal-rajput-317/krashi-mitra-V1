async function resetChat() {
    const crop = document.getElementById("crop").value;
    await fetch(`https://krashi-mitra-v1.onrender.com/reset?crop=${crop}`, { method: "POST" });
    document.getElementById("chat").innerHTML = "";
}

// Update selected district from dropdown
function updateDistrict() {
  selectedDistrict = document.getElementById("district-select").value;
  document.getElementById("chat-district-badge").innerText = "📍 " + selectedDistrict;
}

// Ask question — now includes village
async function askQuestion() {
  const q       = document.getElementById("question").value.trim();
  const crop    = document.getElementById("crop").value;
  const village = document.getElementById("village-input") 
                  ? document.getElementById("village-input").value.trim() 
                  : "";
  if (!q) return;

  addBubble(q, "user", "🧑 You");
  document.getElementById("question").value = "";
  addTyping();

  // Combine district + village for location context
  const location = village
    ? `${village} village, ${selectedDistrict} district`
    : `${selectedDistrict} district`;

  try {
    const res = await fetch("https://krashi-mitra-v1.onrender.com/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ q, crop, language: selectedLanguage, district: location })
    });
    const data = await res.json();

    removeTyping();
    addBubble(data.answer, "bot", "🌾 Assistant");
  } catch (err) {
    removeTyping();
    addBubble("Error: Could not reach the server. Is FastAPI running?", "bot", "⚠️ Error");
  }
}