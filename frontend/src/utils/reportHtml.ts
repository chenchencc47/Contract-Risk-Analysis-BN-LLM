import { marked } from "marked";

const ISSUE_ID_INLINE_PATTERN = /[（(]\s*ISSUE-[A-Za-z0-9_-]+\s*[)）]/g;
const ISSUE_ID_PREFIX_PATTERN = /\bISSUE-[A-Za-z0-9_-]+\b\s*[：:]?\s*/g;
const ISSUE_ID_LABEL_PATTERN = /\b(?:风险ID|Issue ID|IssueID)\b\s*[：:]?\s*/gi;

function stripInternalIds(text: string): string {
  return text
    .replace(ISSUE_ID_INLINE_PATTERN, "")
    .replace(ISSUE_ID_PREFIX_PATTERN, "")
    .replace(ISSUE_ID_LABEL_PATTERN, "");
}

function stripInternalIdsFromDocument(doc: Document): void {
  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
  const textNodes: Text[] = [];
  let currentNode = walker.nextNode();

  while (currentNode) {
    textNodes.push(currentNode as Text);
    currentNode = walker.nextNode();
  }

  textNodes.forEach((node) => {
    const original = node.textContent ?? "";
    const cleaned = stripInternalIds(original);
    if (cleaned !== original) {
      node.textContent = cleaned;
    }
  });
}

function removeEmptyLeadingColumns(doc: Document): void {
  Array.from(doc.querySelectorAll("table")).forEach((table) => {
    const rows = Array.from(table.querySelectorAll("tr"));
    const firstCells = rows
      .map((row) => row.children.item(0) as HTMLTableCellElement | null)
      .filter((cell): cell is HTMLTableCellElement => cell !== null);

    if (firstCells.length > 0 && firstCells.every((cell) => !(cell.textContent?.trim()))) {
      firstCells.forEach((cell) => cell.remove());
    }
  });
}

export function enhanceReportHtml(markdown: string): string {
  const rawHtml = marked.parse(markdown, { async: false }) as string;
  if (typeof window === "undefined") return rawHtml;

  const parser = new DOMParser();
  const doc = parser.parseFromString(rawHtml, "text/html");
  stripInternalIdsFromDocument(doc);
  removeEmptyLeadingColumns(doc);

  Array.from(doc.querySelectorAll("h2")).forEach((heading, index) => {
    heading.classList.add(index === 0 ? "report-title" : "report-h1");
  });

  Array.from(doc.querySelectorAll("h3")).forEach((heading) => {
    const text = heading.textContent?.trim() ?? "";
    if (/^风险\d+/.test(text)) {
      heading.classList.add("report-risk-title");
      heading.setAttribute(
        "data-risk-level",
        text.includes("P1") ? "critical" : text.includes("P2") ? "high" : text.includes("P3") ? "medium" : "default",
      );
    } else {
      heading.classList.add("report-h2");
    }
  });

  Array.from(doc.querySelectorAll("h4")).forEach((heading) => {
    heading.classList.add("report-h3");
  });

  Array.from(doc.querySelectorAll("p")).forEach((paragraph) => {
    const text = paragraph.textContent?.trim() ?? "";
    if (text.includes("核心建议是：")) {
      paragraph.classList.add("report-key-conclusion");
    }
  });

  Array.from(doc.querySelectorAll("strong")).forEach((strong) => {
    const text = strong.textContent?.trim() ?? "";
    if (/\d/.test(text) || text.includes("%") || text.includes("倍") || text.includes("万元")) {
      strong.classList.add("report-metric");
    }
    if (/底线/.test(text)) {
      strong.classList.add("report-bottom-line-tag");
    }
    if (/^(?:签署建议|修改底线|谈判底线|风险底线|合规底线)/.test(text)) {
      strong.classList.add("report-section-label");
    }
  });

  // Catch bold labels inside paragraphs that serve as inline section headers
  Array.from(doc.querySelectorAll("p")).forEach((p) => {
    const firstStrong = p.querySelector("strong");
    if (!firstStrong) return;
    const label = firstStrong.textContent?.trim() ?? "";
    if (label.endsWith("：") || label.endsWith(":")) {
      const bare = label.replace(/[：:]\s*$/, "");
      if (/底线|签署建议|修改方案|条款原文|法律依据|筹码分析|对手预判|风险提示|注意事项|整改/.test(bare)) {
        p.classList.add("report-labeled-paragraph");
      }
    }
  });

  Array.from(doc.querySelectorAll("li")).forEach((item) => {
    const label = item.querySelector("strong")?.textContent?.trim() ?? "";
    if (label.startsWith("条款原文")) {
      item.classList.add("report-clause-original");
    }
    if (/^(?:修改方案|修改建议|建议修改|推荐措辞)/.test(label)) {
      item.classList.add("report-callout-block", "report-callout-modify");
    }
    if (/^(?:法律依据|法律引用|法条依据|相关法条)/.test(label)) {
      item.classList.add("report-callout-block", "report-callout-legal");
    }
    if (/^(?:筹码分析|筹码|谈判筹码)/.test(label)) {
      item.classList.add("report-callout-block", "report-callout-chip");
    }
    if (/^(?:对手预判|对方可能|对方立场)/.test(label)) {
      item.classList.add("report-callout-block", "report-callout-opponent");
    }
    if (/^(?:签署建议|签署底线|底线)/.test(label)) {
      item.classList.add("report-callout-block", "report-callout-bottomline");
    }
  });

  Array.from(doc.querySelectorAll("table")).forEach((table) => {
    const wrapper = doc.createElement("div");
    wrapper.className = "report-table-scroll";
    table.parentNode?.insertBefore(wrapper, table);
    wrapper.appendChild(table);

    Array.from(table.querySelectorAll("th, td")).forEach((cell) => {
      const tableCell = cell as HTMLTableCellElement;
      const text = tableCell.textContent?.trim() ?? "";
      if (tableCell.cellIndex === 0) {
        tableCell.classList.add("report-cell-first");
      } else if (/\d/.test(text) || /^P\d/.test(text) || /^(?:🔴|🟠|🟡|✅)/u.test(text)) {
        tableCell.classList.add("report-cell-numeric");
      } else {
        tableCell.classList.add("report-cell-text");
      }
    });
  });

  Array.from(doc.querySelectorAll("h3.report-risk-title")).forEach((heading) => {
    const wrapper = doc.createElement("section");
    const level = heading.getAttribute("data-risk-level") ?? "default";
    wrapper.className = `report-risk-section report-risk-${level}`;
    heading.parentNode?.insertBefore(wrapper, heading);

    let current: ChildNode | null = heading;
    while (current) {
      const next: ChildNode | null = current.nextSibling;
      wrapper.appendChild(current);
      if (next && next.nodeType === Node.ELEMENT_NODE) {
        const nextElement = next as Element;
        if (nextElement.tagName === "H2" || nextElement.tagName === "H3") {
          break;
        }
      }
      current = next;
    }
  });

  return doc.body.innerHTML;
}
