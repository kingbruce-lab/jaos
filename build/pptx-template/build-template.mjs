import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const OUT = "C:/Users/86185/Documents/New project/jingao-copilot/agent/assets/jingao-proposal-template.pptx";
const LOGO = "C:/Users/86185/Documents/New project/jingao-copilot/public/jingao-logo.jpg";
const PREVIEW_DIR = "C:/Users/86185/Documents/New project/jingao-copilot/build/pptx-template/previews";

const W = 1280;
const H = 720;
const C = {
  navy: "#111722",
  navy2: "#172945",
  ink: "#211D1B",
  muted: "#687184",
  line: "#E3E6EB",
  paper: "#F4F5F7",
  white: "#FFFFFF",
  red: "#D91E2B",
  redSoft: "#FFF0F1",
  blue: "#155DA4",
  blueSoft: "#EAF3FB",
  green: "#18854B",
  greenSoft: "#EAF7F0",
  orange: "#EE9618",
  orangeSoft: "#FFF5E5",
};
const FONT = "Microsoft YaHei";

async function imageBlob(filePath) {
  const bytes = await fs.readFile(filePath);
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}

function addText(slide, name, text, position, style = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name,
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = {
    fontFamily: FONT,
    fontSize: 20,
    color: C.ink,
    ...style,
  };
  return shape;
}

function addRect(slide, name, position, fill, options = {}) {
  return slide.shapes.add({
    geometry: options.geometry || "rect",
    name,
    position,
    fill,
    line: options.line || { style: "solid", fill: "none", width: 0 },
    ...(options.borderRadius ? { borderRadius: options.borderRadius } : {}),
  });
}

async function addLogo(slide, logoBytes, dark = false) {
  if (dark) {
    addRect(slide, "logo-white-frame", { left: 78, top: 54, width: 182, height: 73 }, C.white, {
      geometry: "roundRect",
      borderRadius: "rounded-lg",
    });
  }
  slide.images.add({
    blob: logoBytes.slice(0),
    contentType: "image/jpeg",
    alt: "京奥电竞 LOGO",
    fit: "contain",
    position: dark
      ? { left: 88, top: 61, width: 162, height: 59 }
      : { left: 1035, top: 39, width: 165, height: 66 },
  });
}

function addBrandLine(slide) {
  const width = W / 4;
  [C.blue, C.red, C.green, C.orange].forEach((fill, index) => {
    addRect(slide, `brand-line-${index}`, { left: width * index, top: 0, width, height: 6 }, fill);
  });
}

async function addHeader(slide, logoBytes, section, title, page) {
  slide.background.fill = C.white;
  addBrandLine(slide);
  addText(slide, `section-${page}`, section, { left: 80, top: 48, width: 420, height: 24 }, {
    fontSize: 13,
    bold: true,
    color: C.red,
    letterSpacing: 1.5,
  });
  addText(slide, `title-${page}`, title, { left: 80, top: 91, width: 920, height: 62 }, {
    fontSize: 38,
    bold: true,
    color: C.ink,
  });
  await addLogo(slide, logoBytes, false);
}

function addFooter(slide, page, sourceToken) {
  addRect(slide, `footer-line-${page}`, { left: 80, top: 656, width: 1120, height: 1 }, C.line);
  addText(slide, `source-${page}`, sourceToken, { left: 80, top: 668, width: 1010, height: 20 }, {
    fontSize: 11,
    color: C.muted,
  });
  addText(slide, `page-${page}`, String(page).padStart(2, "0"), { left: 1120, top: 666, width: 80, height: 22 }, {
    fontSize: 12,
    bold: true,
    color: C.red,
    alignment: "right",
  });
}

function setNotes(slide, token) {
  slide.speakerNotes.textFrame.setText(`[Sources]\n${token}`);
  slide.speakerNotes.setVisible(true);
}

function addBullet(slide, page, index, token, top, color = C.ink) {
  addRect(slide, `bullet-mark-${page}-${index}`, { left: 92, top: top + 10, width: 9, height: 9 }, index % 2 ? C.blue : C.red, {
    geometry: "ellipse",
  });
  addText(slide, `bullet-${page}-${index}`, token, { left: 122, top, width: 1010, height: 52 }, {
    fontSize: 22,
    color,
  });
}

async function main() {
  await fs.mkdir(path.dirname(OUT), { recursive: true });
  await fs.mkdir(PREVIEW_DIR, { recursive: true });
  const logoBytes = await imageBlob(LOGO);
  const deck = Presentation.create({ slideSize: { width: W, height: H } });

  // 1. Minimal cover.
  {
    const slide = deck.slides.add();
    slide.background.fill = C.navy;
    addBrandLine(slide);
    await addLogo(slide, logoBytes, true);
    addText(slide, "cover-eyebrow", "{{COVER_EYEBROW}}", { left: 80, top: 196, width: 780, height: 30 }, {
      fontSize: 16,
      bold: true,
      color: "#FF6971",
      letterSpacing: 2,
    });
    addText(slide, "cover-title", "{{COVER_TITLE}}", { left: 80, top: 246, width: 930, height: 150 }, {
      fontSize: 54,
      bold: true,
      color: C.white,
    });
    addText(slide, "cover-subtitle", "{{COVER_SUBTITLE}}", { left: 84, top: 420, width: 850, height: 48 }, {
      fontSize: 24,
      color: "#C6CFDE",
    });
    addText(slide, "cover-meta", "{{COVER_META}}", { left: 84, top: 590, width: 820, height: 30 }, {
      fontSize: 15,
      color: "#8E9AAF",
    });
    addRect(slide, "cover-accent", { left: 1040, top: 232, width: 8, height: 248 }, C.red);
    addText(slide, "cover-draft", "内部可编辑初稿", { left: 1073, top: 333, width: 125, height: 56 }, {
      fontSize: 15,
      bold: true,
      color: "#FF6971",
      alignment: "center",
    });
    setNotes(slide, "{{S1_NOTES}}");
  }

  // 2. Requirement understanding.
  {
    const slide = deck.slides.add();
    await addHeader(slide, logoBytes, "01 / REQUIREMENT", "{{S2_TITLE}}", 2);
    addText(slide, "s2-intro", "{{S2_INTRO}}", { left: 80, top: 178, width: 1080, height: 58 }, {
      fontSize: 24,
      bold: true,
      color: C.blue,
    });
    for (let index = 1; index <= 5; index += 1) {
      addBullet(slide, 2, index, `{{S2_LINE${index}}}`, 255 + (index - 1) * 68);
    }
    addFooter(slide, 2, "{{S2_SOURCE}}");
    setNotes(slide, "{{S2_NOTES}}");
  }

  // 3. Objectives as a stepped sequence.
  {
    const slide = deck.slides.add();
    await addHeader(slide, logoBytes, "02 / OBJECTIVES", "{{S3_TITLE}}", 3);
    const tops = [205, 337, 469];
    const fills = [C.blue, C.red, C.green];
    for (let index = 0; index < 3; index += 1) {
      addText(slide, `s3-number-${index}`, `0${index + 1}`, { left: 84, top: tops[index], width: 86, height: 66 }, {
        fontSize: 44,
        bold: true,
        color: fills[index],
      });
      addRect(slide, `s3-rule-${index}`, { left: 186, top: tops[index] + 26, width: 56, height: 3 }, fills[index]);
      addText(slide, `s3-head-${index}`, `{{S3_HEAD${index + 1}}}`, { left: 276, top: tops[index], width: 310, height: 40 }, {
        fontSize: 25,
        bold: true,
        color: C.ink,
      });
      addText(slide, `s3-body-${index}`, `{{S3_BODY${index + 1}}}`, { left: 595, top: tops[index], width: 565, height: 66 }, {
        fontSize: 19,
        color: C.muted,
      });
    }
    addFooter(slide, 3, "{{S3_SOURCE}}");
    setNotes(slide, "{{S3_NOTES}}");
  }

  // 4. Four-stage solution path. Arrows are created before nodes.
  {
    const slide = deck.slides.add();
    await addHeader(slide, logoBytes, "03 / SOLUTION", "{{S4_TITLE}}", 4);
    const nodeLefts = [92, 368, 644, 920];
    for (let index = 0; index < 3; index += 1) {
      addRect(slide, `s4-arrow-${index}`, { left: nodeLefts[index] + 174, top: 326, width: 86, height: 28 }, "#CFD6E0", {
        geometry: "rightArrow",
      });
    }
    const colors = [C.blue, C.red, C.green, C.orange];
    for (let index = 0; index < 4; index += 1) {
      addRect(slide, `s4-node-${index}`, { left: nodeLefts[index], top: 242, width: 174, height: 196 }, C.white, {
        geometry: "roundRect",
        borderRadius: "rounded-xl",
        line: { style: "solid", fill: colors[index], width: 2 },
      });
      addText(slide, `s4-step-${index}`, `0${index + 1}`, { left: nodeLefts[index] + 21, top: 263, width: 58, height: 34 }, {
        fontSize: 18,
        bold: true,
        color: colors[index],
      });
      addText(slide, `s4-head-${index}`, `{{S4_HEAD${index + 1}}}`, { left: nodeLefts[index] + 20, top: 309, width: 134, height: 38 }, {
        fontSize: 24,
        bold: true,
        color: C.ink,
        alignment: "center",
      });
      addText(slide, `s4-body-${index}`, `{{S4_BODY${index + 1}}}`, { left: nodeLefts[index] + 18, top: 363, width: 138, height: 55 }, {
        fontSize: 16,
        color: C.muted,
        alignment: "center",
      });
    }
    addText(slide, "s4-conclusion", "{{S4_CONCLUSION}}", { left: 190, top: 498, width: 900, height: 54 }, {
      fontSize: 22,
      bold: true,
      color: C.blue,
      alignment: "center",
    });
    addFooter(slide, 4, "{{S4_SOURCE}}");
    setNotes(slide, "{{S4_NOTES}}");
  }

  // 5. Curriculum and activity design.
  {
    const slide = deck.slides.add();
    await addHeader(slide, logoBytes, "04 / CONTENT", "{{S5_TITLE}}", 5);
    const lefts = [80, 365, 650, 935];
    const colors = [C.blue, C.red, C.green, C.orange];
    for (let index = 0; index < 4; index += 1) {
      addText(slide, `s5-index-${index}`, `0${index + 1}`, { left: lefts[index], top: 206, width: 70, height: 48 }, {
        fontSize: 30,
        bold: true,
        color: colors[index],
      });
      addRect(slide, `s5-rule-${index}`, { left: lefts[index], top: 272, width: 220, height: 4 }, colors[index]);
      addText(slide, `s5-head-${index}`, `{{S5_HEAD${index + 1}}}`, { left: lefts[index], top: 301, width: 230, height: 66 }, {
        fontSize: 25,
        bold: true,
        color: C.ink,
      });
      addText(slide, `s5-body-${index}`, `{{S5_BODY${index + 1}}}`, { left: lefts[index], top: 385, width: 230, height: 118 }, {
        fontSize: 17,
        color: C.muted,
      });
    }
    addText(slide, "s5-output", "{{S5_OUTPUT}}", { left: 80, top: 550, width: 1120, height: 50 }, {
      fontSize: 21,
      bold: true,
      color: C.red,
    });
    addFooter(slide, 5, "{{S5_SOURCE}}");
    setNotes(slide, "{{S5_NOTES}}");
  }

  // 6. Execution timeline. Lines created before milestone nodes.
  {
    const slide = deck.slides.add();
    await addHeader(slide, logoBytes, "05 / DELIVERY", "{{S6_TITLE}}", 6);
    addRect(slide, "s6-line", { left: 152, top: 332, width: 956, height: 4 }, "#CFD6E0");
    const lefts = [140, 448, 756, 1064];
    const colors = [C.blue, C.red, C.green, C.orange];
    for (let index = 0; index < 4; index += 1) {
      addRect(slide, `s6-dot-${index}`, { left: lefts[index], top: 316, width: 36, height: 36 }, colors[index], {
        geometry: "ellipse",
      });
      addText(slide, `s6-head-${index}`, `{{S6_HEAD${index + 1}}}`, { left: lefts[index] - 92, top: 225, width: 220, height: 50 }, {
        fontSize: 23,
        bold: true,
        color: C.ink,
        alignment: "center",
      });
      addText(slide, `s6-time-${index}`, `{{S6_TIME${index + 1}}}`, { left: lefts[index] - 82, top: 275, width: 200, height: 28 }, {
        fontSize: 15,
        bold: true,
        color: colors[index],
        alignment: "center",
      });
      addText(slide, `s6-body-${index}`, `{{S6_BODY${index + 1}}}`, { left: lefts[index] - 96, top: 384, width: 228, height: 92 }, {
        fontSize: 16,
        color: C.muted,
        alignment: "center",
      });
    }
    addText(slide, "s6-coordination", "{{S6_COORDINATION}}", { left: 170, top: 525, width: 940, height: 50 }, {
      fontSize: 20,
      bold: true,
      color: C.blue,
      alignment: "center",
    });
    addFooter(slide, 6, "{{S6_SOURCE}}");
    setNotes(slide, "{{S6_NOTES}}");
  }

  // 7. Evaluation and closing.
  {
    const slide = deck.slides.add();
    await addHeader(slide, logoBytes, "06 / EVALUATION", "{{S7_TITLE}}", 7);
    const top = [203, 314, 425, 536];
    const colors = [C.blue, C.red, C.green, C.orange];
    for (let index = 0; index < 4; index += 1) {
      addText(slide, `s7-index-${index}`, `0${index + 1}`, { left: 86, top: top[index], width: 60, height: 43 }, {
        fontSize: 27,
        bold: true,
        color: colors[index],
      });
      addText(slide, `s7-head-${index}`, `{{S7_HEAD${index + 1}}}`, { left: 178, top: top[index], width: 280, height: 43 }, {
        fontSize: 23,
        bold: true,
        color: C.ink,
      });
      addText(slide, `s7-body-${index}`, `{{S7_BODY${index + 1}}}`, { left: 470, top: top[index], width: 680, height: 54 }, {
        fontSize: 18,
        color: C.muted,
      });
      if (index < 3) {
        addRect(slide, `s7-rule-${index}`, { left: 178, top: top[index] + 78, width: 972, height: 1 }, C.line);
      }
    }
    addFooter(slide, 7, "{{S7_SOURCE}}");
    setNotes(slide, "{{S7_NOTES}}");
  }

  // 8. Risks and decisions.
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    addBrandLine(slide);
    await addLogo(slide, logoBytes, false);
    addText(slide, "s8-section", "07 / DECISIONS", { left: 80, top: 48, width: 420, height: 24 }, {
      fontSize: 13,
      bold: true,
      color: C.red,
      letterSpacing: 1.5,
    });
    addText(slide, "s8-title", "{{S8_TITLE}}", { left: 80, top: 91, width: 900, height: 62 }, {
      fontSize: 38,
      bold: true,
      color: C.ink,
    });
    addRect(slide, "s8-left", { left: 80, top: 192, width: 540, height: 394 }, C.white, {
      geometry: "roundRect",
      borderRadius: "rounded-xl",
      line: { style: "solid", fill: "#E4E7EC", width: 1 },
    });
    addRect(slide, "s8-right", { left: 660, top: 192, width: 540, height: 394 }, C.navy2, {
      geometry: "roundRect",
      borderRadius: "rounded-xl",
    });
    addText(slide, "s8-left-head", "提交前待确认", { left: 112, top: 225, width: 430, height: 42 }, {
      fontSize: 26,
      bold: true,
      color: C.red,
    });
    addText(slide, "s8-right-head", "可参考的历史候选", { left: 692, top: 225, width: 430, height: 42 }, {
      fontSize: 26,
      bold: true,
      color: C.white,
    });
    for (let index = 1; index <= 4; index += 1) {
      addText(slide, `s8-left-${index}`, `{{S8_MISSING${index}}}`, { left: 112, top: 292 + (index - 1) * 64, width: 452, height: 47 }, {
        fontSize: 18,
        color: C.muted,
      });
      addText(slide, `s8-right-${index}`, `{{S8_CASE${index}}}`, { left: 692, top: 292 + (index - 1) * 64, width: 452, height: 47 }, {
        fontSize: 18,
        color: "#D5DDE9",
      });
    }
    addText(slide, "s8-close", "{{S8_CLOSE}}", { left: 80, top: 612, width: 1040, height: 34 }, {
      fontSize: 19,
      bold: true,
      color: C.blue,
    });
    addFooter(slide, 8, "{{S8_SOURCE}}");
    setNotes(slide, "{{S8_NOTES}}");
  }

  for (const [index, slide] of deck.slides.items.entries()) {
    const blob = await deck.export({ slide, format: "png", scale: 1 });
    await fs.writeFile(path.join(PREVIEW_DIR, `template-${index + 1}.png`), new Uint8Array(await blob.arrayBuffer()));
  }
  const pptx = await PresentationFile.exportPptx(deck);
  await pptx.save(OUT);
  console.log(JSON.stringify({ output: OUT, slides: deck.slides.items.length }));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
