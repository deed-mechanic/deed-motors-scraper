// DEED MOTORS DMS 連携用エクスポートスクリプト
// 査定ツール画面のDOM実際のIDから値を読み取り、JSONとしてクリップボードにコピーする。
// 詳細仕様: deed_motors_scraper_export_spec.md

function exportAppraisalData(){
  try {
    exportAppraisalDataInner();
  } catch (e) {
    // JSON組み立て中に何らかのエラーが起きても、何も表示されないまま終わらせない
    console.error("exportAppraisalData failed:", e);
    showExportFeedback(false, "（データの読み取り中にエラーが発生しました: " + (e && e.message || e) + "）");
  }
}

function exportAppraisalDataInner(){
  const val = id => { const el = document.getElementById(id); return el ? el.value.trim() : ""; };
  const text = id => { const el = document.getElementById(id); return el ? el.textContent.trim() : ""; };
  const num = s => {
    if (s === null || s === undefined) return null;
    const m = String(s).replace(/,/g, "").match(/-?\d+(\.\d+)?/);
    return m ? parseFloat(m[0]) : null;
  };
  const selLabel = id => {
    const el = document.getElementById(id);
    return (el && el.selectedIndex > 0) ? el.options[el.selectedIndex].text : "";
  };

  // 車名（自由入力欄）を「メーカー / 車種」に分割（例: "Toyota Harrier" → Toyota / Harrier）
  const carName = val("carName");
  const [carNameMaker, ...carNameModelParts] = carName.split(/\s+/).filter(Boolean);
  const carNameModel = carNameModelParts.join(" ");

  // 第二部の市場価格プルダウン（選択済みならこちらの表記を優先）
  const makerLabel = selLabel("maker") || carNameMaker || "";
  const modelLabel = selLabel("modelSlug") || carNameModel || "";

  // 生産年月「2018年3月 / 2018он 3-р сар」→ 2018
  const mfgDate = val("mfgDate");
  const mfgYearMatch = mfgDate.match(/(\d{4})/);
  const carYearVal = num(val("carYear"));
  const manufactureYear = mfgYearMatch ? parseInt(mfgYearMatch[1], 10) : carYearVal;

  // 駆動方式
  const driveTypeVal = val("driveType");
  const drivetrain = driveTypeVal === "4wd" ? "4WD" : driveTypeVal === "2wd" ? "2WD" : "";

  // 修復歴（ツール内部の状態変数 RV から取得。RVはメインスクリプトのグローバルスコープで定義済み）
  const histStatus = (typeof RV !== "undefined" && RV.rHist) ? RV.rHist : "none";

  // 修復歴部位（該当箇所）：チェック済みの .hist-part-cb から日本語ラベルのみ取得
  // （value属性は "日本語 / モンゴル語" 形式。モンゴル語部分が無い項目もあるためsplitで先頭のみ使う）
  const affectedParts = Array.from(document.querySelectorAll(".hist-part-cb:checked"))
    .map(cb => cb.value.split("/")[0].trim())
    .filter(Boolean);

  // 市場価格プレビュー（#mktPreview 内の 平均/最低/最高/件数、個別IDが無いため出現順で取得）
  let averagePriceManMnt = null, minPriceManMnt = null, maxPriceManMnt = null, sampleCount = null;
  const mktStrongs = document.querySelectorAll("#mktPreview .mkt-nums strong");
  if (mktStrongs.length >= 4) {
    averagePriceManMnt = num(mktStrongs[0].textContent);
    minPriceManMnt     = num(mktStrongs[1].textContent);
    maxPriceManMnt      = num(mktStrongs[2].textContent);
    sampleCount          = num(mktStrongs[3].textContent);
  }

  // 査定参考価格レンジ「レンジ / Хүрээ: 22.5 〜 30.0 сая ₮」
  const rangeText = text("rcRange");
  const rangeMatch = rangeText.match(/([\d.]+)\s*[〜~]\s*([\d.]+)/);

  const payload = {
    source: "deed-motors-scraper",
    exportedAt: new Date().toISOString(),

    vehicle: {
      registrationNumber: val("regNum"),
      maker: makerLabel,
      model: modelLabel,
      fullModel: val("fullModel"),
      trimGrade: val("carGrade"),
      vin: val("vinNum"),
      engineModel: val("engType"),
      displacementCc: num(val("displacement")),
      color: val("bodyColor"),
      mileageKm: num(val("mileageVal")),
      manufactureYear: manufactureYear,
      importedYearMonth: val("mnImport"),
      registrationStatus: "",
      inspector: val("inspector"),
      appraisalDate: val("assessDate")
    },

    damageHistory: {
      status: histStatus,
      affectedParts: affectedParts
    },

    score: {
      grade: text("gradeBadge"),
      totalScore: num(text("scoreNum")),
      totalDeduction: num(text("deductNum")),
      totalBonus: num(text("addedNum"))
    },

    marketPrice: {
      makerModel: [makerLabel, modelLabel].filter(Boolean).join(" "),
      productionYear: carYearVal,
      drivetrain: drivetrain,
      averagePriceManMnt: averagePriceManMnt,
      minPriceManMnt: minPriceManMnt,
      maxPriceManMnt: maxPriceManMnt,
      sampleCount: sampleCount,
      dataAsOf: ""
    },

    finalAppraisal: {
      referencePriceManMnt: num(text("rcPrice")),
      rangeLowManMnt: rangeMatch ? parseFloat(rangeMatch[1]) : null,
      rangeHighManMnt: rangeMatch ? parseFloat(rangeMatch[2]) : null,
      formula: text("rcFormula")
    }
  };

  const jsonText = JSON.stringify(payload, null, 2);

  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(jsonText)
        .then(() => showExportFeedback(true, jsonText))
        .catch(() => showExportFeedback(false, jsonText));
    } else {
      showExportFeedback(false, jsonText);
    }
  } catch (e) {
    showExportFeedback(false, jsonText);
  }
}

// 結果をページ内に常に表示する（alert/promptはFacebook内ブラウザ等の埋め込みWebViewで
// サイレントに無効化されることがあり、その場合「ボタンを押しても何も起きない」ように
// 見えてしまうため、ネイティブダイアログに頼らずDOM表示でフィードバックする）
function showExportFeedback(success, jsonText) {
  const el = document.getElementById("exportFeedback");
  if (!el) {
    // フォールバック（要素が見つからない旧バージョンのページ向け）
    if (success) alert("査定結果をコピーしました。DEED MOTORS DMSの車両登録画面に貼り付けてください。");
    else prompt("コピーに失敗しました。以下を手動でコピーしてください:", jsonText);
    return;
  }
  el.innerHTML = "";
  el.style.display = "block";
  if (success) {
    el.style.background = "#e8f5e9";
    el.style.border = "1.5px solid #4caf50";
    el.style.color = "#2e7d32";
    el.textContent = "✅ 査定結果をコピーしました。DEED MOTORS DMSの車両登録画面に貼り付けてください。 / Үнэлгээний үр дүнг хууллаа.";
  } else {
    el.style.background = "#fff3e0";
    el.style.border = "1.5px solid #ff9800";
    el.style.color = "#e65100";
    const msg = document.createElement("div");
    msg.textContent = "⚠️ 自動コピーができませんでした。下のテキストを選択（長押し）してコピーしてください。";
    const ta = document.createElement("textarea");
    ta.readOnly = true;
    ta.value = jsonText;
    ta.style.cssText = "width:100%;height:100px;margin-top:6px;font-size:11px;font-family:monospace;box-sizing:border-box;";
    ta.onclick = () => ta.select();
    el.appendChild(msg);
    el.appendChild(ta);
  }
}
