(function exposeThinkTankI18n(root) {
  const locales = {
    fa: {
      "app.title": "دفتر پرونده | اتاق فکر",
      "app.brand": "اتاق فکر",
      "app.live": "زنده",
      "app.offline": "آفلاین",
      "app.closed": "بسته",
      "app.connecting": "در حال اتصال",
      "app.refresh": "بروزرسانی",
      "app.settings": "تنظیمات پرونده",
      "app.close": "بستن",
      "app.saved": "ذخیره شد",
      "app.sendError": "خطا در ارسال",
      "app.untitled": "پرونده بدون عنوان",

      "header.caseOpen": "پرونده باز",
      "header.caseClosed": "پرونده بسته",
      "header.openFindings": "یافته باز",
      "header.round": "دور",
      "header.searchPlaceholder": "جستجو در پرونده‌ها…",
      "header.switchSession": "انتخاب پرونده",
      "header.statusOpen": "باز",
      "header.statusClosed": "بسته",
      "header.currentSession": "پرونده جاری",
      "header.newRun": "اجرای جدید",
      "header.runsTitle": "اجراهای این گفت‌وگو",
      "header.runBadge": "اجرا",

      "empty.badge": "آماده",
      "empty.title": "این گفت‌وگو پرونده‌ای ندارد",
      "empty.desc": "با شروع کار چندایجنتی یا واگذاری وظیفه در این گفت‌وگو، پرونده به‌طور خودکار ثبت می‌شود.",
      "empty.convIdLabel": "شناسه گفت‌وگو:",
      "empty.initBtn": "ساخت دستی پرونده",

      "nav.ariaLabel": "نماهای پرونده",
      "nav.flow": "جریان",
      "nav.map": "نقشه و بازپخش",
      "nav.team": "تیم",

      "flow.now.title": "الان",
      "flow.now.idle": "تیم بیکار است",
      "flow.now.lastEvent": "آخرین رویداد",
      "flow.now.moreActivity": "فعالیت دیگر",
      "flow.now.awaitingUser": "منتظر شما",
      "flow.now.reviewBtn": "بررسی",
      "flow.now.workingOn": "در حال کار روی",
      "flow.now.triageLabel": "تصمیم مسیر",
      "flow.now.triageThinkTank": "ورود به اتاق فکر",
      "flow.now.triageSolo": "انجام مستقیم",

      "flow.bars.findingsLabel": "یافته‌ها",
      "flow.bars.wbsLabel": "کارهای WBS",
      "flow.bars.clearFilter": "حذف فیلتر",
      "flow.bars.open": "باز",
      "flow.bars.fixing": "در اصلاح",
      "flow.bars.inReview": "در بازبینی",
      "flow.bars.testing": "در تست",
      "flow.bars.verified": "تأییدشده",
      "flow.bars.wontfix": "صرف‌نظر",
      "flow.bars.assigned": "واگذارشده",
      "flow.bars.inProgress": "در انجام",
      "flow.bars.completed": "تکمیل‌شده",

      "flow.findings.title": "یافته‌ها",
      "flow.findings.empty": "هنوز یافته‌ای ثبت نشده است.",
      "flow.findings.emptyFiltered": "یافته‌ای با این وضعیت وجود ندارد.",
      "flow.findings.verifiedDrawer": "تأییدشده و بسته‌شده",
      "flow.findings.pinImportant": "مهم برای من",
      "flow.findings.returns": "برگشت",
      "flow.findings.eventsCount": "رویداد",
      "flow.findings.noEvidence": "هنوز مدرک QA ثبت نشده است.",
      "flow.findings.reproSteps": "سناریوی بازتولید",
      "flow.findings.wontFixReason": "دلیل صرف‌نظر",
      "flow.findings.state.Open": "باز",
      "flow.findings.state.Fixing": "در اصلاح",
      "flow.findings.state.InReview": "در بازبینی",
      "flow.findings.state.Testing": "در تست",
      "flow.findings.state.Verified": "تأییدشده",
      "flow.findings.state.Closed": "بسته",
      "flow.findings.state.WontFix": "صرف‌نظر",
      "flow.findings.sev.CRITICAL": "بحرانی",
      "flow.findings.sev.HIGH": "بالا",
      "flow.findings.sev.MEDIUM": "متوسط",
      "flow.findings.sev.LOW": "کم",
      "flow.findings.rail.open": "باز",
      "flow.findings.rail.fixing": "اصلاح",
      "flow.findings.rail.inReview": "بازبینی",
      "flow.findings.rail.testing": "تست",
      "flow.findings.rail.verified": "تأیید",

      "flow.wbs.title": "کارهای WBS",
      "flow.wbs.empty": "هنوز موردی در WBS ثبت نشده است.",
      "flow.wbs.acceptance": "معیار پذیرش:",
      "flow.wbs.lockedFiles": "فایل‌های قفل‌شده",
      "flow.wbs.openFindings": "یافته باز",

      "flow.ledger.title": "دفتر رویدادها",
      "flow.ledger.empty": "رویدادی با این فیلتر ثبت نشده است.",
      "flow.ledger.filter.ALL": "همه",
      "flow.ledger.filter.FINDINGS": "یافته‌ها",
      "flow.ledger.filter.QA": "QA",
      "flow.ledger.filter.SYNC": "سینک",
      "flow.ledger.filter.TASKS": "WBS",
      "flow.ledger.filter.USER": "پیام‌های من",
      "flow.ledger.searchPlaceholder": "جستجو در #seq، شناسه یافته یا متن…",
      "flow.ledger.origin.subagent": "ساب‌ایجنت واقعی",
      "flow.ledger.origin.main-proxy": "ثبت از طرف ایجنت اصلی",
      "flow.ledger.origin.user": "کاربر",

      "flow.composer.senderLabel": "فرستنده:",
      "flow.composer.senderYou": "شما",
      "flow.composer.targetLabel": "مخاطب",
      "flow.composer.targetTeam": "همه اعضای تیم",
      "flow.composer.placeholder": "پیام یا نظر خود را برای تیم بنویسید…",
      "flow.composer.send": "ارسال",
      "flow.empty.initDirective": "آماده دریافت مأموریت",
      "flow.decision.approve": "تایید پیشنهاد",
      "flow.decision.revise": "درخواست اصلاح",
      "flow.decision.revisionPlaceholder": "توضیح اصلاحیه مورد نظر…",
      "flow.decision.sendRevision": "ارسال اصلاحیه",
      "flow.decision.cancel": "انصراف",
      "flow.decision.verifiedClosed": "بررسی‌شده و بسته",
      "flow.decision.reviewTitle": "تصمیم بازبینی تیم (اطمینان زیر ۹۵٪)",
      "flow.decision.continueBtn": "ادامهٔ کار",
      "flow.decision.stopBtn": "توقف کار",
      "flow.decision.notePlaceholder": "یادداشت اختیاری برای تیم…",
      "flow.now.triageReasons": "دلایل تفکیک",

      "receipt.title": "پرونده بسته شد",
      "receipt.events": "رویداد",
      "receipt.tasksLabel": "کارها",
      "receipt.tasksFormat": "{done} از {total} تکمیل",
      "receipt.findingsLabel": "یافته‌ها",
      "receipt.findingsFormat": "{verified} تأیید · {open} باز · {wontfix} صرف‌نظر",
      "receipt.qaLabel": "مدرک QA",
      "receipt.qaFormat": "{runs} اجرا · {status}",
      "receipt.qaAllZero": "همه موفق (کد خروج ۰)",
      "receipt.qaHasFail": "دارای خطا",
      "receipt.qaNone": "بدون اجرا",
      "receipt.originsLabel": "منبع رویدادها",
      "receipt.originsFormat": "{subagent} ساب‌ایجنت · {proxy} از طرف اصلی · {user} کاربر",
      "receipt.forceReason": "دلیل بستن اجباری:",
      "receipt.wontFixTitle": "موارد صرف‌نظرشده:",
      "receipt.replayBtn": "دیدن بازپخش",
      "receipt.reopenCase": "بازگشایی پرونده",
      "receipt.newCaseBtn": "شروع پرونده جدید",

      "inspector.title": "بازرس پرونده",
      "inspector.emptyHint": "روی یک یافته یا سطر رویداد کلیک کنید تا رشته کامل و مدرک در اینجا باز شود.",
      "inspector.close": "بستن بازرس",
      "inspector.threadHeading": "رشته رویدادها",
      "inspector.evidenceHeading": "مدارک QA",
      "inspector.exitCode": "کد خروج",
      "inspector.hash": "هش خروجی",
      "inspector.runner": "محیط اجرا",
      "inspector.runnerReason": "دلیل",
      "inspector.command": "فرمان",
      "inspector.detailHeading": "جزئیات پیام",
      "inspector.requestType": "نوع درخواست",
      "inspector.whatDone": "کار انجام‌شده",
      "inspector.participants": "مسیر تعامل",
      "inspector.edgeHeading": "تعاملات این فلش",
      "inspector.openEvent": "مشاهده جزئیات",
      "inspector.noEdgeEvents": "رویدادی روی این مسیر ثبت نشده است.",
      "inspector.reasoning": "استدلال",
      "inspector.critique": "نقد",
      "inspector.question": "پرسش",
      "inspector.report": "گزارش",

      "map.title": "نقشه و بازپخش",
      "map.subview.sequence": "توالی",
      "map.subview.network": "شبکه",
      "map.empty": "هنوز تعاملی برای نمایش ثبت نشده است.",
      "map.table.from": "از",
      "map.table.to": "به",
      "map.table.count": "تعداد",
      "map.table.open": "یافته باز",
      "map.replay.prev": "گام قبل",
      "map.replay.play": "پخش",
      "map.replay.pause": "توقف",
      "map.replay.next": "گام بعد",
      "map.replay.speed": "سرعت",
      "map.replay.live": "زنده",
      "map.replay.behind": "بازپخش · {n} رویداد جدیدتر",
      "map.replay.shortcuts": "Space پخش/توقف · چپ/راست گام · L زنده",
      "map.sr.caption": "جدول توالی رویدادهای پرونده",
      "map.sr.seq": "شماره",
      "map.sr.from": "از",
      "map.sr.to": "به",
      "map.sr.action": "اقدام",
      "map.sr.finding": "یافته",
      "map.sr.status": "وضعیت",
      "map.legend.ariaLabel": "راهنمای رنگ موضوعات",
      "map.legend.referral": "ارجاع و واگذاری",
      "map.legend.inquiry": "پرسش و بازخواست",
      "map.legend.defect": "نقد و برگشت ایراد",
      "map.legend.rewrite": "اصلاح و بازنویسی",
      "map.legend.sync": "سینک همتا و پیام",
      "map.legend.verify": "آزمون QA و تأیید",
      "map.tier.supervisors": "سرگروه‌ها",
      "map.tier.tester": "تستر QA",
      "map.tier.workers": "متخصصان",

      "team.title": "اعضای تیم",
      "team.filter.all": "همه",
      "team.filter.supervisor": "سرگروه‌ها",
      "team.filter.tester": "تستر QA",
      "team.filter.worker": "متخصصان",
      "team.inactiveDrawer": "در این پرونده فعال نشدند",
      "team.turnsUsed": "دور مصرف‌شده",
      "team.activeTool": "ابزار فعال",
      "team.skillsLabel": "مهارت‌ها",
      "team.lockedFiles": "فایل‌های قفل‌شده",
      "team.recentEvents": "رویدادهای اخیر",
      "team.noEvents": "رویدادی برای این نقش ثبت نشده است.",
      "team.msgAgent": "پیام به این ایجنت",
      "team.verifiedSubagent": "زیرعامل واقعی",

      "settings.title": "تنظیمات پرونده",
      "settings.close": "بستن تنظیمات",
      "settings.switchCaseSection": "تغییر پرونده",
      "settings.sessionSection": "پروژه و دستور کار",
      "settings.projectLabel": "نام پروژه",
      "settings.projectPlaceholder": "نام پروژه یا ماژول",
      "settings.directiveLabel": "دستور کار",
      "settings.directivePlaceholder": "هدف و دامنه این پرونده",
      "settings.saveSession": "ذخیره پرونده",
      "settings.extendRounds": "+۳ دور",
      "settings.reconnect": "اتصال مجدد",
      "settings.completeCaseBtn": "تأیید نهایی و بستن پرونده",
      "settings.forceCloseLabel": "بستن اجباری با دلیل (وقتی یافته باز باقی مانده):",
      "settings.forceClosePlaceholder": "دلیل بستن با یافته باز…",
      "settings.capsSection": "سقف دور نقش‌ها",
      "settings.capMain": "عامل اصلی",
      "settings.capManager": "مدیر تیم",
      "settings.capSubagents": "زیرعامل‌ها",
      "settings.saveCaps": "ذخیره سقف‌ها",
      "settings.usageOf": "مصرف {used} از {cap}",
      "settings.prefsSection": "نمایش و زبان",
      "settings.languageLabel": "زبان رابط",
      "settings.themeLabel": "پوسته",
      "settings.themeDark": "تیره",
      "settings.themeLight": "روشن",
      "settings.devModeLabel": "حالت توسعه‌دهنده",
      "settings.devModeHint": "نمایش شناسه نشست، منبع دقیق و بازرس JSON خام",
      "settings.rawTitle": "داده‌های خام پرونده (JSON)",
      "settings.rawCopy": "کپی JSON",
      "settings.rawCopied": "کپی شد",

      "action.RETURN_DEFECT": "ایراد برگشتی",
      "action.QA_REOPEN": "بازگشایی QA",
      "action.WORKER_FIX": "اصلاحیه",
      "action.REVIEW_QUERY": "پرسش بررسی",
      "action.INTERROGATE": "بازخواست",
      "action.INTERROGATE_REPLY": "پاسخ بازخواست",
      "action.CRITIQUE": "نقد و بررسی",
      "action.QA_DISPATCH": "دستور تست",
      "action.QA_REPORT": "گزارش QA",
      "action.PEER_SYNC": "سینک همتا",
      "action.DELEGATE": "واگذاری",
      "action.ASSIGN_SUBTASK": "تخصیص ریزتسک",
      "action.SUBTASK_UPDATE": "به‌روزرسانی ریزتسک",
      "action.APPROVE": "تأیید",
      "action.DECIDE": "تصمیم‌گیری",
      "action.PROPOSAL": "پیشنهاد",
      "action.COMPLETE": "تکمیل پرونده",
      "action.GOVERNANCE": "حاکمیت",
      "action.REVISION_REQUESTED": "درخواست بازنگری",
      "action.MESSAGE": "پیام",
      "action.QUESTION": "سوال / استعلام",
      "action.DECISION": "تصمیم‌گیری",
      "action.REWRITE": "بازنویسی / اصلاح",
      "action.REFERRAL": "ارجاع / واگذاری",
      "action.INTERROGATION": "پرسش و بازخواست",
      "action.DEFECT_RETURN": "ایراد برگشتی",
      "tooltip.roleHint": "نمایش نام دوزبانه نقش",
      "reqType.REWRITE": "بازنویسی / اصلاح",
      "reqType.REFERRAL": "ارجاع / واگذاری",
      "reqType.QUESTION": "سوال / استعلام",
      "reqType.INTERROGATION": "پرسش و بازخواست",
      "reqType.DEFECT_RETURN": "برگشت ایراد",
      "reqType.CRITIQUE": "نقد و بررسی",
      "reqType.QA_REPORT": "گزارش آزمون QA",
      "reqType.PEER_SYNC": "هم‌فکری و سینک",
      "reqType.DECISION": "تصمیم / تأیید",
      "reqType.MESSAGE": "پیام مستقیم",
    },
    en: {
      "app.title": "Case Ledger | Think Tank",
      "app.brand": "Think Tank",
      "app.live": "Live",
      "app.offline": "Offline",
      "app.closed": "Closed",
      "app.connecting": "Connecting",
      "app.refresh": "Refresh",
      "app.settings": "Case Settings",
      "app.close": "Close",
      "app.saved": "Saved",
      "app.sendError": "Send failed",
      "app.untitled": "Untitled Case",

      "header.caseOpen": "Open case",
      "header.caseClosed": "Closed case",
      "header.openFindings": "open findings",
      "header.round": "Round",
      "header.searchPlaceholder": "Search cases…",
      "header.switchSession": "Select case",
      "header.statusOpen": "Open",
      "header.statusClosed": "Closed",
      "header.currentSession": "Current case",
      "header.newRun": "New Run",
      "header.runsTitle": "Conversation Runs",
      "header.runBadge": "Run",

      "empty.badge": "Ready",
      "empty.title": "No active case in this conversation",
      "empty.desc": "A case is created automatically when multi-agent orchestration or task delegation starts in this conversation.",
      "empty.convIdLabel": "Conversation ID:",
      "empty.initBtn": "Create Case Manually",

      "nav.ariaLabel": "Case views",
      "nav.flow": "Flow",
      "nav.map": "Map & Replay",
      "nav.team": "Team",

      "flow.now.title": "Now",
      "flow.now.idle": "Team is idle",
      "flow.now.lastEvent": "Last event",
      "flow.now.moreActivity": "more active",
      "flow.now.awaitingUser": "Awaiting you",
      "flow.now.reviewBtn": "Review",
      "flow.now.workingOn": "working on",
      "flow.now.triageLabel": "Routing triage",
      "flow.now.triageThinkTank": "Use ThinkTank",
      "flow.now.triageSolo": "Direct execution",

      "flow.bars.findingsLabel": "Findings",
      "flow.bars.wbsLabel": "WBS Tasks",
      "flow.bars.clearFilter": "Clear filter",
      "flow.bars.open": "Open",
      "flow.bars.fixing": "Fixing",
      "flow.bars.inReview": "In Review",
      "flow.bars.testing": "Testing",
      "flow.bars.verified": "Verified",
      "flow.bars.wontfix": "Won't Fix",
      "flow.bars.assigned": "Assigned",
      "flow.bars.inProgress": "In Progress",
      "flow.bars.completed": "Completed",

      "flow.findings.title": "Findings",
      "flow.findings.empty": "No findings recorded yet.",
      "flow.findings.emptyFiltered": "No findings match this state.",
      "flow.findings.verifiedDrawer": "Verified & Closed",
      "flow.findings.pinImportant": "Important to me",
      "flow.findings.returns": "returns",
      "flow.findings.eventsCount": "events",
      "flow.findings.noEvidence": "No QA evidence recorded yet.",
      "flow.findings.reproSteps": "Reproduction steps",
      "flow.findings.wontFixReason": "Withdrawal reason",
      "flow.findings.state.Open": "Open",
      "flow.findings.state.Fixing": "Fixing",
      "flow.findings.state.InReview": "In Review",
      "flow.findings.state.Testing": "Testing",
      "flow.findings.state.Verified": "Verified",
      "flow.findings.state.Closed": "Closed",
      "flow.findings.state.WontFix": "Won't Fix",
      "flow.findings.sev.CRITICAL": "Critical",
      "flow.findings.sev.HIGH": "High",
      "flow.findings.sev.MEDIUM": "Medium",
      "flow.findings.sev.LOW": "Low",
      "flow.findings.rail.open": "Open",
      "flow.findings.rail.fixing": "Fix",
      "flow.findings.rail.inReview": "Review",
      "flow.findings.rail.testing": "Test",
      "flow.findings.rail.verified": "Verified",

      "flow.wbs.title": "WBS Work Items",
      "flow.wbs.empty": "No WBS work items recorded yet.",
      "flow.wbs.acceptance": "Acceptance criteria:",
      "flow.wbs.lockedFiles": "Locked files",
      "flow.wbs.openFindings": "open findings",

      "flow.ledger.title": "Event Ledger",
      "flow.ledger.empty": "No events match this filter.",
      "flow.ledger.filter.ALL": "All",
      "flow.ledger.filter.FINDINGS": "Findings",
      "flow.ledger.filter.QA": "QA",
      "flow.ledger.filter.SYNC": "Sync",
      "flow.ledger.filter.TASKS": "Tasks",
      "flow.ledger.filter.USER": "My messages",
      "flow.ledger.searchPlaceholder": "Search #seq, finding ID, or text…",
      "flow.ledger.origin.subagent": "Real subagent",
      "flow.ledger.origin.main-proxy": "Logged by main agent",
      "flow.ledger.origin.user": "User",

      "flow.composer.senderLabel": "From:",
      "flow.composer.senderYou": "You",
      "flow.composer.targetLabel": "Recipient",
      "flow.composer.targetTeam": "All team members",
      "flow.composer.placeholder": "Write a message or note to the team…",
      "flow.composer.send": "Send",
      "flow.empty.initDirective": "Ready to receive directive",
      "flow.decision.approve": "Approve Proposal",
      "flow.decision.revise": "Request Revision",
      "flow.decision.revisionPlaceholder": "Describe requested revision…",
      "flow.decision.sendRevision": "Send Revision",
      "flow.decision.cancel": "Cancel",
      "flow.decision.verifiedClosed": "Reviewed & Closed",
      "flow.decision.reviewTitle": "Team Review Decision (<95% Confidence)",
      "flow.decision.continueBtn": "Continue Work",
      "flow.decision.stopBtn": "Stop Work",
      "flow.decision.notePlaceholder": "Optional note for the team…",
      "flow.now.triageReasons": "Triage reasons",

      "receipt.title": "Case Closed",
      "receipt.events": "events",
      "receipt.tasksLabel": "Tasks",
      "receipt.tasksFormat": "{done} of {total} completed",
      "receipt.findingsLabel": "Findings",
      "receipt.findingsFormat": "{verified} verified · {open} open · {wontfix} won't fix",
      "receipt.qaLabel": "QA Evidence",
      "receipt.qaFormat": "{runs} runs · {status}",
      "receipt.qaAllZero": "all exit 0",
      "receipt.qaHasFail": "failures recorded",
      "receipt.qaNone": "no runs",
      "receipt.originsLabel": "Event Origins",
      "receipt.originsFormat": "{subagent} subagent · {proxy} main-proxy · {user} user",
      "receipt.forceReason": "Force-close reason:",
      "receipt.wontFixTitle": "Withdrawn findings:",
      "receipt.replayBtn": "View Replay",
      "receipt.reopenCase": "Reopen case",
      "receipt.newCaseBtn": "Start New Case",

      "inspector.title": "Case Inspector",
      "inspector.emptyHint": "Select a finding or ledger row to inspect its full thread and QA evidence.",
      "inspector.close": "Close inspector",
      "inspector.threadHeading": "Event Thread",
      "inspector.evidenceHeading": "QA Evidence",
      "inspector.exitCode": "Exit code",
      "inspector.hash": "Output hash",
      "inspector.runner": "Runner",
      "inspector.runnerReason": "Reason",
      "inspector.command": "Command",
      "inspector.detailHeading": "Event Detail",
      "inspector.requestType": "Request Type",
      "inspector.whatDone": "Action Performed",
      "inspector.participants": "Route",
      "inspector.edgeHeading": "Arrow Interactions",
      "inspector.openEvent": "Inspect Event",
      "inspector.noEdgeEvents": "No interactions recorded along this arrow.",
      "inspector.reasoning": "Reasoning",
      "inspector.critique": "Critique",
      "inspector.question": "Question",
      "inspector.report": "Report",

      "map.title": "Map & Replay",
      "map.subview.sequence": "Sequence",
      "map.subview.network": "Network",
      "map.empty": "No recorded interactions yet.",
      "map.table.from": "From",
      "map.table.to": "To",
      "map.table.count": "Count",
      "map.table.open": "Open",
      "map.replay.prev": "Prev",
      "map.replay.play": "Play",
      "map.replay.pause": "Pause",
      "map.replay.next": "Next",
      "map.replay.speed": "Speed",
      "map.replay.live": "Live",
      "map.replay.behind": "Replay · {n} newer events",
      "map.replay.shortcuts": "Space Play/Pause · Left/Right Step · L Live",
      "map.sr.caption": "Case interaction sequence table",
      "map.sr.seq": "Seq",
      "map.sr.from": "From",
      "map.sr.to": "To",
      "map.sr.action": "Action",
      "map.sr.finding": "Finding",
      "map.sr.status": "Status",
      "map.legend.ariaLabel": "Topic color legend",
      "map.legend.referral": "Delegation / Referral",
      "map.legend.inquiry": "Question / Interrogation",
      "map.legend.defect": "Critique / Defect Return",
      "map.legend.rewrite": "Rewrite / Fix",
      "map.legend.sync": "Peer Sync / Message",
      "map.legend.verify": "QA / Decision",
      "map.tier.supervisors": "Supervisors",
      "map.tier.tester": "QA Tester",
      "map.tier.workers": "Specialists",

      "team.title": "Team Roster",
      "team.filter.all": "All",
      "team.filter.supervisor": "Supervisors",
      "team.filter.tester": "QA Tester",
      "team.filter.worker": "Specialists",
      "team.inactiveDrawer": "Inactive in this case",
      "team.turnsUsed": "Turns used",
      "team.activeTool": "Active tool",
      "team.skillsLabel": "Skills",
      "team.lockedFiles": "Locked files",
      "team.recentEvents": "Recent events",
      "team.noEvents": "No events recorded for this role.",
      "team.msgAgent": "Message this agent",
      "team.verifiedSubagent": "Real Subagent",

      "settings.title": "Case Settings",
      "settings.close": "Close settings",
      "settings.switchCaseSection": "Switch Case",
      "settings.sessionSection": "Project & Directive",
      "settings.projectLabel": "Project Name",
      "settings.projectPlaceholder": "Project or module name",
      "settings.directiveLabel": "Directive",
      "settings.directivePlaceholder": "Case scope and objective",
      "settings.saveSession": "Save Case",
      "settings.extendRounds": "+3 Rounds",
      "settings.reconnect": "Reconnect",
      "settings.completeCaseBtn": "Complete & Close Case",
      "settings.forceCloseLabel": "Force-close reason (required if findings remain open):",
      "settings.forceClosePlaceholder": "Reason for closing with open findings…",
      "settings.capsSection": "Role Turn Caps",
      "settings.capMain": "Main Agent",
      "settings.capManager": "Team Manager",
      "settings.capSubagents": "Subagents",
      "settings.saveCaps": "Save Caps",
      "settings.usageOf": "{used} of {cap} used",
      "settings.prefsSection": "Display & Language",
      "settings.languageLabel": "Language",
      "settings.themeLabel": "Theme",
      "settings.themeDark": "Dark",
      "settings.themeLight": "Light",
      "settings.devModeLabel": "Developer Mode",
      "settings.devModeHint": "Reveal conversation ID, raw origin metadata, and JSON inspector",
      "settings.rawTitle": "Raw Case Data (JSON)",
      "settings.rawCopy": "Copy JSON",
      "settings.rawCopied": "Copied",

      "action.RETURN_DEFECT": "Returned Defect",
      "action.QA_REOPEN": "QA Reopen",
      "action.WORKER_FIX": "Worker Fix",
      "action.REVIEW_QUERY": "Review Query",
      "action.INTERROGATE": "Interrogate",
      "action.INTERROGATE_REPLY": "Interrogate Reply",
      "action.CRITIQUE": "Critique",
      "action.QA_DISPATCH": "QA Dispatch",
      "action.QA_REPORT": "QA Report",
      "action.PEER_SYNC": "Peer Sync",
      "action.DELEGATE": "Assign Task",
      "action.ASSIGN_SUBTASK": "Assign Subtask",
      "action.SUBTASK_UPDATE": "Subtask Update",
      "action.APPROVE": "Approve",
      "action.DECIDE": "Decide",
      "action.PROPOSAL": "Proposal",
      "action.COMPLETE": "Complete",
      "action.GOVERNANCE": "Governance",
      "action.REVISION_REQUESTED": "Revision Requested",
      "action.MESSAGE": "Message",
      "action.QUESTION": "Question",
      "action.DECISION": "Decision",
      "action.REWRITE": "Rewrite / Fix",
      "action.REFERRAL": "Referral",
      "action.INTERROGATION": "Interrogation",
      "action.DEFECT_RETURN": "Defect Return",
      "tooltip.roleHint": "Bilingual role name",
      "reqType.REWRITE": "Rewrite / Fix",
      "reqType.REFERRAL": "Referral / Assignment",
      "reqType.QUESTION": "Question / Inquiry",
      "reqType.INTERROGATION": "Interrogation / Audit",
      "reqType.DEFECT_RETURN": "Defect Return",
      "reqType.CRITIQUE": "Critique",
      "reqType.QA_REPORT": "QA Report",
      "reqType.PEER_SYNC": "Peer Sync",
      "reqType.DECISION": "Decision / Approval",
      "reqType.MESSAGE": "Direct Message",
    },
  };

  // Legacy Persian-phrase -> English dictionary kept intact (without emojis)
  const copy = {
    "اتاق فکر (Think Tank)": "Think Tank",
    "اتاق فکر": "Think Tank",
    "اتاق فکر زنده": "Live Think Tank",
    "نمای کلی": "Overview",
    "گفت‌وگوها": "Conversations",
    "اعضای تیم": "Team",
    "تنظیمات": "Settings",
    "بورد تقسیم کار و پیشرفت پروژه": "Work Breakdown & Project Progress Board",
    "ماتریس آراء، توافق و نقدهای شورای ساب‌ایجنت‌ها": "Subagent Council Consensus, Votes & Critiques Matrix",
    "واگذاری تسک": "Assign Task",
    "شروع اجرا": "Start",
    "تکمیل شد": "Complete",
    "پیام": "Message",
    "ثبت نقد": "Critique",
    "پرسش فنی": "Question",
    "رأی شورا": "Council Vote",
    "ایراد برگشتی": "Returned Defect",
    "اصلاحیه کارگر": "Worker Fix",
    "پرسش بررسی و QA": "Review & QA Query",
    "بازخواست": "Interrogate",
    "اعزام QA": "Dispatch QA",
    "نتیجه QA": "QA Report",
    "سینک همتا": "Peer Sync",
    "تایید پیشنهاد": "Approve Proposal",
    "درخواست اصلاح": "Request Revision",
    "توضیح اصلاحیه مورد نظر:": "Enter revision feedback:",
    "بررسی‌شده و بسته": "Verified & Closed",
    "بازبینی و تصمیم شورا": "Council Review & Decision",
    "عضو تیم": "Team Member",
    "در حال اتصال…": "Connecting…",
    "در حال اتصال": "Connecting",
    "آفلاین": "Offline",
    "زنده": "Live",
    "تکمیل‌شده": "Completed",
    "بستن": "Close",
    "ارسال": "Send",
    "بروزرسانی": "Refresh",
    "همه": "All",
    "سرگروه‌ها": "Supervisors",
    "تستر QA": "QA Tester",
    "متخصصان": "Specialists",
    "آماده دریافت مأموریت": "Ready for directive",
    "تغییر پوسته": "Change theme",
    "زبان": "Language",
    "کپی شد": "Copied",
    "ذخیره شد": "Saved",
    "خطا در ارسال": "Failed to send",
    "۳ دور جدید اضافه شد": "Added 3 new rounds",
    "تنظیمات نشست ذخیره شد": "Session settings saved",
    "سقف دور نقش‌ها ذخیره شد": "Role turn caps saved",
    "پروژه بدون عنوان": "Untitled case",
    "هم‌اندیشی زنده": "Live collaboration",
    "فعال": "Active",
    "در حال کار": "Working",
    "در صف / واگذارشده": "Assigned",
    "در حال انجام": "In Progress",
    "در حال بازبینی": "In Review",
    "آماده": "Idle",
    "متوقف": "Paused",
    "مسدود": "Blocked",
    "قطع اتصال": "Disconnected",
  };

  const roleEnglish = {
    main_agent: ["Main Agent", "Task direction, triage, and final delivery", "Understands the user request, evaluates ThinkTank vs solo execution honestly, coordinates the 7+1 team, and delivers verified output."],
    "team-manager": ["Team Manager", "WBS decomposition, orchestration, and interrogation", "Breaks tasks into clean WBS subtasks, enforces single-owner editing, interrogates progress, and coordinates quality gates."],
    team_manager: ["Team Manager", "WBS decomposition, orchestration, and interrogation", "Breaks tasks into clean WBS subtasks, enforces single-owner editing, interrogates progress, and coordinates quality gates."],
    manager: ["Team Manager", "WBS decomposition, orchestration, and interrogation", "Breaks tasks into clean WBS subtasks, enforces single-owner editing, interrogates progress, and coordinates quality gates."],
    "council-critic": ["Council Critic", "Relentless flaw, security & AI-slop hunting", "Exclusively hunts logical bugs, architectural flaws, security risks, workflow gaps, and AI slop, interrogating specialists directly."],
    council_critic: ["Council Critic", "Relentless flaw, security & AI-slop hunting", "Exclusively hunts logical bugs, architectural flaws, security risks, workflow gaps, and AI slop, interrogating specialists directly."],
    critic: ["Council Critic", "Relentless flaw, security & AI-slop hunting", "Exclusively hunts logical bugs, architectural flaws, security risks, workflow gaps, and AI slop, interrogating specialists directly."],
    "code-reviewer": ["Code Reviewer", "Line-by-line code audit & QA commander", "Reviews every diff line by line, demands concrete evidence, commands subordinate qa-reviewer, and interrogates implementers."],
    code_reviewer: ["Code Reviewer", "Line-by-line code audit & QA commander", "Reviews every diff line by line, demands concrete evidence, commands subordinate qa-reviewer, and interrogates implementers."],
    reviewer: ["Code Reviewer", "Line-by-line code audit & QA commander", "Reviews every diff line by line, demands concrete evidence, commands subordinate qa-reviewer, and interrogates implementers."],
    "qa-reviewer": ["QA & Test Reviewer", "Subordinate test execution & edge-case QA", "Reports directly to Code Reviewer; runs unit, integration, E2E, responsive, and regression tests with concrete pass/fail reports."],
    qa_reviewer: ["QA & Test Reviewer", "Subordinate test execution & edge-case QA", "Reports directly to Code Reviewer; runs unit, integration, E2E, responsive, and regression tests with concrete pass/fail reports."],
    "ui-frontend-designer": ["UI & Frontend Architect", "Design systems, Hallmark anti-slop & RTL UI", "Sole owner of UI, UX, responsive layout, motion, dark mode, accessibility, and frontend code while strictly rejecting AI clichés."],
    ui_frontend_designer: ["UI & Frontend Architect", "Design systems, Hallmark anti-slop & RTL UI", "Sole owner of UI, UX, responsive layout, motion, dark mode, accessibility, and frontend code while strictly rejecting AI clichés."],
    designer_solver: ["UI & Frontend Architect", "Design systems, Hallmark anti-slop & RTL UI", "Sole owner of UI, UX, responsive layout, motion, dark mode, accessibility, and frontend code while strictly rejecting AI clichés."],
    "backend-auditor": ["Backend & Core Logic Engineer", "APIs, databases, security, Cloudflare & Firebase", "Sole owner of backend services, database schemas, auth/RBAC security, Cloudflare edge infrastructure, and Firebase rules."],
    backend_auditor: ["Backend & Core Logic Engineer", "APIs, databases, security, Cloudflare & Firebase", "Sole owner of backend services, database schemas, auth/RBAC security, Cloudflare edge infrastructure, and Firebase rules."],
    security_reviewer: ["Security Specialist", "Threats, access, and data protection", "Reviews trust boundaries, permissions, inputs, and data retention, then states risks precisely."],
    ecommerce_seo_operator: ["E-Commerce Product SEO Specialist", "Product SEO, schema & high-CTR Persian copy", "Optimizes store catalogs, JSON-LD schema, NeuronWriter NLP semantic coverage, and high-CTR persuasive product copywriting."],
    seo_specialist: ["E-Commerce Product SEO Specialist", "Product SEO, schema & high-CTR Persian copy", "Optimizes store catalogs, JSON-LD schema, NeuronWriter NLP semantic coverage, and high-CTR persuasive product copywriting."],
    wp_technical_operator: ["WooCommerce & WordPress SRE", "Server health, MySQL/Redis, gateways & safe WP-CLI", "Diagnoses query bottlenecks, database autoload health, Redis caching, payment webhooks, and read-only-first catalog audits."],
  };

  const skillNames = {
    "accessibility-qa": "Accessibility QA",
    "agent-evaluation": "Agent evaluation",
    "agent-output-scoring": "Agent output scoring",
    "agents-sdk": "Agents SDK",
    "backend-engineering": "Backend engineering",
    "backend-quality": "Backend quality",
    "browser-check": "Browser testing",
    cloudflare: "Cloudflare",
    "cloudflare-developer-suite": "Cloudflare Developer Suite",
    "cloudflare-one": "Cloudflare One",
    "cloudflare-security-sase": "Cloudflare Security & SASE",
    "codebase-exploration": "Codebase exploration",
    "content-editing": "Content editing",
    "content-operations": "Content operations",
    "context-budget": "Context budgeting",
    "context-cost-control": "Context & cost control",
    copywriting: "High-CTR Copywriting",
    "dark-mode-visuals": "Dark mode design",
    "data-intake-tiering": "Data intake & tiering",
    "deep-research": "Deep research",
    "design-director": "Design director",
    "design-handoff": "Design handoff",
    "design-to-code": "Design to code",
    "design-tokens": "Design tokens",
    "documentation-researcher": "Documentation research",
    "durable-objects": "Durable Objects",
    "engineering-director": "Engineering director",
    "evidence-verification": "Evidence verification",
    figma: "Figma",
    "find-skills": "Skill discovery",
    firebase: "Firebase",
    "firebase-master": "Firebase Master Suite",
    "firebase-security-rules-auditor": "Firebase security rules auditor",
    firecrawl: "Firecrawl web extraction",
    "firestore-rules-author": "Firestore rules",
    "firestore-rules-creation": "Firestore rules creation",
    "flutter-a11y": "Flutter accessibility",
    "flutter-build-responsive-layout": "Flutter responsive layout",
    "frontend-quality": "Frontend quality",
    hallmark: "Hallmark anti-slop design",
    imagegen: "Image generation",
    "ios-inspired-components": "Tactile iOS components",
    "jev-decision-layer": "JEV decision layer",
    localization: "Localization",
    microinteractions: "Microinteractions",
    "motion-design": "Motion design",
    neuronwriter: "NeuronWriter NLP SEO",
    "perfume-ecommerce-seo": "Luxury & E-Commerce SEO",
    "persian-first-copy": "Persian-first writing",
    ponytail: "Ponytail minimal diff",
    "quality-gate": "Quality gate",
    "receiving-code-review": "Code review response",
    "requirements-traceability": "Requirements traceability",
    "research-compact": "Compact research",
    "research-director": "Research director",
    "responsive-layout": "Responsive layout",
    "risk-analysis": "Risk analysis",
    "sandbox-sdk": "Sandbox SDK",
    "security-review": "Security review",
    "seo-optimizer": "SEO optimizer",
    "skill-coaching": "Skill coaching",
    "skill-creator": "Skill authoring",
    "subq-decision-layer": "SubQ decision layer",
    "task-orchestration": "Task orchestration",
    "task-router": "Task routing",
    "telegram-agent-director": "Telegram agent director",
    "telegram-channel-director": "Telegram channel management",
    "telegram-management": "Telegram management",
    "test-driven-development": "Test-driven development",
    "think-room": "Think Tank collaboration",
    "translation-review": "Translation review",
    "verification-before-completion": "Pre-completion verification",
    "web-perf": "Web performance",
    "woo-catalog-manager": "WooCommerce catalog management",
    "woo-ecommerce-director": "WooCommerce E-Commerce Director",
    "woocommerce-technical-operator": "WooCommerce operations",
    "workers-best-practices": "Workers best practices",
    "wp-commerce-ops": "WP Commerce Operations",
    "wp-content-editor": "WordPress content editing",
    "wp-integration-guide": "WordPress integration",
    "wp-operations-safe": "Safe WordPress operations",
    "wp-performance-diagnostics": "WordPress performance diagnostics",
    "wp-search-analytics": "Search analytics",
    "wp-security-guardian": "WordPress security",
    "wp-security-review": "WordPress security review",
    "wp-seo-auditor": "SEO auditing",
    "wp-seo-content-engine": "WP Technical & NLP SEO Engine",
    "wp-seo-editor": "SEO editing",
    "wp-technical-operator": "WordPress technical operations",
    "wp-technical-ops-sre": "WordPress & WooCommerce SRE",
  };

  const originals = new WeakMap();
  const attributeOriginals = new WeakMap();
  const liveLabels = new Set();
  let language = "fa";

  function tKey(key, locale = language, vars = null) {
    const lang = locale === "en" ? "en" : "fa";
    let str = locales[lang]?.[key];
    if (str === undefined) str = locales.fa[key];
    if (str === undefined) return key;
    if (vars && typeof vars === "object") {
      for (const [k, v] of Object.entries(vars)) {
        str = str.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
      }
    }
    return str;
  }

  function translate(value, locale = language) {
    if (typeof value !== "string") return value;
    const lang = locale === "en" ? "en" : "fa";
    if (locales[lang] && value in locales[lang]) return locales[lang][value];
    if (lang !== "en") return value;
    return copy[value] || value;
  }

  function roleText(role, field, locale = language) {
    if (!role || typeof role !== "object") return "";
    const translated = locale === "en" ? roleEnglish[role.id] : null;
    if (translated) {
      const index = { title: 0, specialty: 1, description: 2 }[field];
      if (index !== undefined) return translated[index];
    }
    return role[field] || "";
  }

  function formatNumber(value, locale = language) {
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value);
    return number.toLocaleString(locale === "en" ? "en-US" : "fa-IR");
  }

  function setLocalizedText(element, keyOrPersianText) {
    if (!element || typeof keyOrPersianText !== "string") return;
    element.dataset.ttFaText = keyOrPersianText;
    liveLabels.add(element);
    element.textContent = translate(keyOrPersianText, language);
  }

  function translateStaticContent(locale) {
    if (typeof document === "undefined") return;
    const lang = locale === "en" ? "en" : "fa";

    for (const el of document.querySelectorAll("[data-i18n]")) {
      const key = el.getAttribute("data-i18n");
      if (key) el.textContent = tKey(key, lang);
    }

    for (const el of document.querySelectorAll("[data-i18n-attr]")) {
      const spec = el.getAttribute("data-i18n-attr") || "";
      for (const pair of spec.split(",")) {
        const [attr, key] = pair.split(":").map((s) => s && s.trim());
        if (attr && key) el.setAttribute(attr, tKey(key, lang));
      }
    }

    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let textNode;
    while ((textNode = walker.nextNode())) {
      const parent = textNode.parentElement;
      if (!parent || parent.closest("[data-i18n], [data-tt-fa-text], [data-tt-dynamic], [dir=auto], .mono-id, .mono-code, #messages-feed, #team-list, #raw-json-viewer, #findings-list, #verified-findings-list, #wbs-list, #case-inspector")) continue;
      if (!originals.has(textNode)) originals.set(textNode, textNode.nodeValue);
      const original = originals.get(textNode);
      const content = original.trim();
      const translated = lang === "en" ? translate(content, lang) : content;
      if (translated !== content) {
        const leading = original.match(/^\s*/)?.[0] || "";
        const trailing = original.match(/\s*$/)?.[0] || "";
        textNode.nodeValue = `${leading}${translated}${trailing}`;
      } else {
        textNode.nodeValue = original;
      }
    }

    const translatableAttributes = ["aria-label", "aria-description", "placeholder", "title"];
    for (const element of document.querySelectorAll("body *")) {
      if (element === document.getElementById("language-toggle") || element.hasAttribute("data-i18n-attr")) continue;
      let saved = attributeOriginals.get(element);
      if (!saved) { saved = {}; attributeOriginals.set(element, saved); }
      for (const attribute of translatableAttributes) {
        if (!element.hasAttribute(attribute)) continue;
        if (!(attribute in saved)) saved[attribute] = element.getAttribute(attribute);
        element.setAttribute(attribute, translate(saved[attribute], lang));
      }
    }

    for (const element of [...liveLabels]) {
      if (!element.isConnected) { liveLabels.delete(element); continue; }
      element.textContent = translate(element.dataset.ttFaText, lang);
    }
  }

  function applyLanguage(locale = "fa", notify = false) {
    language = locale === "en" ? "en" : "fa";
    if (typeof document === "undefined") return language;
    document.documentElement.lang = language;
    document.documentElement.dir = language === "en" ? "ltr" : "rtl";
    document.documentElement.dataset.language = language;
    document.title = tKey("app.title", language);
    translateStaticContent(language);
    if (notify && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("thinktank:languagechange", { detail: { language } }));
    }
    return language;
  }

  function getLanguage() {
    if (typeof window === "undefined") return "fa";
    try { return localStorage.getItem("thinktank-language") === "en" ? "en" : "fa"; }
    catch { return "fa"; }
  }

  function setLanguage(locale) {
    const chosen = locale === "en" ? "en" : "fa";
    try { localStorage.setItem("thinktank-language", chosen); } catch { /* noop */ }
    return applyLanguage(chosen, true);
  }

  const api = { locales, tKey, translate, roleText, formatNumber, setLocalizedText, applyLanguage, getLanguage, setLanguage, skillNames };
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) {
    root.ThinkTankI18n = api;
    applyLanguage(getLanguage());
  }
})(typeof window !== "undefined" ? window : (typeof globalThis !== "undefined" ? globalThis : null));
