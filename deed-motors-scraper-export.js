// DEED MOTORS DMS 連携用エクスポートスクリプト
// 査定ツール画面のDOM実際のIDから値を読み取り、JSONとしてクリップボードにコピーする。
// 詳細仕様: deed_motors_scraper_export_spec.md

function exportAppraisalData(){
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
      affectedParts: []
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

  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(jsonText)
      .then(() => alert("査定結果をコピーしました。DEED MOTORS DMSの車両登録画面に貼り付けてください。\nҮнэлгээний үр дүнг хууллаа. DEED MOTORS DMS-ийн машин бүртгэх дэлгэц рүү буулгана уу."))
      .catch(() => prompt("コピーに失敗しました。以下を手動でコピーしてください:", jsonText));
  } else {
    prompt("以下をコピーしてください:", jsonText);
  }
}
