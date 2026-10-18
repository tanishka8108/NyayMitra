/* =========================================================
   मराठी शब्दकोश (MARATHI DICTIONARY)

   Same flat keys as en.ts. Written for the legal-civic
   register used across Maharashtra's courts — formal but
   plain Marathi, with established legal terms (वकील,
   न्यायालय, खटला) rather than literal calques. Keys must
   stay in parity with en.ts (enforced by i18n.test.ts).
   ========================================================= */

export const mr: Record<string, string> = {
  /* ---- ॲप क्रोम (सेशन बार / साइन-आउट कोन) ---- */
  "app.signOut": "साइन आउट",
  "app.role.user": "वापरकर्ता",
  "app.role.lawyer": "वकील",
  "app.role.admin": "प्रशासक",
  "app.role.staff": "कर्मचारी",
  "app.theme.toggleGroup": "थीम",
  "app.theme.toDark": "गडद थीममध्ये बदला",
  "app.theme.toLight": "उजळ थीममध्ये बदला",
  "app.lang.group": "भाषा",

  /* ---- भूमिका डॅशबोर्ड शैल ---- */
  "roleDashboard.badge.open": "उघडा",
  "roleDashboard.badge.soon": "लवकर येत आहे",
  "roleDashboard.cta.open": "विभाग उघडा →",
  "roleDashboard.cta.underDevelopment": "विकासाधीन",

  /* ---- लॉगिन पृष्ठ ---- */
  "login.brand.tagline": "एआय कोर्ट सहाय्यक",
  "login.eyebrow": "एक मंच • चार भूमिका",
  "login.hero.title1": "तुमचे स्वागत आहे",
  "login.hero.titleAccent": "NyayMitra.",
  "login.hero.copy":
    "एकच लॉगिन प्रणाली तुम्ही वापरकर्ता, वकील, " +
    "प्रशासक किंवा कर्मचारी आहात हे ओळखते — आणि " +
    "तुमच्या भूमिकेसाठी तयार केलेले डॅशबोर्ड उघडते.",
  "login.doors.label": "साइन इन",
  "login.doors.heading": "कोणत्या भूमिकेत लॉग इन?",
  "login.doors.sub": "तुमच्या भूमिकेशी जुळणारा दरवाजा निवडा.",
  "login.door.user.title": "मी नागरिक आहे",
  "login.door.user.role": "वापरकर्ता",
  "login.door.user.desc":
    "खटले शोधा, वेळापत्रक पाहा, न्यायालयीन आदेश " +
    "वाचा, वकील शोधा आणि कायदेशीर दस्तऐवज " +
    "अनुवादित करा.",
  "login.door.lawyer.title": "मी वकील आहे",
  "login.door.lawyer.role": "वकील",
  "login.door.lawyer.desc":
    "तुमचे व्यावसायिक प्रोफाइल, खटले, तक्रारी आणि " +
    "ग्राहक संवाद व्यवस्थापित करा.",
  "login.door.admin.title": "मी प्रशासक आहे",
  "login.door.admin.role": "प्रशासक",
  "login.door.admin.desc":
    "वापरकर्ते, वकील, कर्मचारी आणि मंचाचा प्रवेश " +
    "व्यवस्थापित करा. कर्मचारी याच दरवाज्यातून " +
    "साइन इन करतात.",
  "login.door.cta": "पुढे जा →",
  "login.registerLink": "नवीन नागरिक? खाते तयार करा →",
  "login.demo.show": "डेमो खाती दाखवा",
  "login.demo.hide": "डेमो खाती लपवा",
  "login.demo.label": "डेमो खाती — मॉक प्रमाणीकरण",
  "login.demo.use": "वापरा",
  "login.eyebrow.staff": "कर्मचारी साइन-इन",
  "login.eyebrow.door": "{role} साइन-इन",
  "login.staff.title1": "कर्मचारी प्रवेश",
  "login.staff.titleAccent": "प्रशासकाद्वारे.",
  "login.form.title1": "साइन इन करा",
  "login.form.titleAccent": "तुमच्या डॅशबोर्डमध्ये.",
  "login.staff.desc":
    "कर्मचारी खाती प्रशासकाद्वारे तयार केली जातात " +
    "व त्यांचे व्यवस्थापन केले जाते. तुम्हाला दिलेल्या " +
    "खात्याची माहितीने साइन इन करा.",
  "login.back": "← भूमिका बदला",
  "login.label.staff": "कर्मचारी",
  "login.heading.staff": "कर्मचारी साइन-इन",
  "login.heading.as": "{role} म्हणून साइन इन करा",
  "login.staffLink": "तुम्ही कर्मचारी आहात? इथे साइन इन करा →",
  "login.adminBack": "← प्रशासक साइन-इन",
  "login.field.staffEmail": "कर्मचारी ईमेल",
  "login.field.identifier": "ईमेल किंवा वापरकर्ता आयडी",
  "login.field.placeholder.staff": "you@nyaymitra.in",
  "login.field.placeholder.mock": "you@example.com किंवा USER_0001",
  "login.field.placeholder": "you@example.com",
  "login.field.password": "पासवर्ड",
  "login.field.passwordPlaceholder": "तुमचा पासवर्ड टाका",
  "login.password.show": "पासवर्ड दाखवा",
  "login.password.hide": "पासवर्ड लपवा",
  "login.password.showShort": "दाखवा",
  "login.password.hideShort": "लपवा",
  "login.error.staffEmail": "कृपया तुमचा कर्मचारी ईमेल टाका.",
  "login.error.identifier": "कृपया ईमेल किंवा वापरकर्ता आयडी टाका.",
  "login.error.password": "कृपया तुमचा पासवर्ड टाका.",
  "login.error.generic": "साइन इन करता आले नाही. कृपया पुन्हा प्रयत्न करा.",
  "login.submit.loading": "भूमिका तपासत आहे...",
  "login.submit.staff": "कर्मचारी म्हणून साइन इन करा",
  "login.submit.as": "{role} म्हणून साइन इन करा",
  "login.note.mock": "प्रमाणीकरण मॉक मोडमध्ये चालू आहे. ",
  "login.note.tail":
    "साइन-इनवर तुमची भूमिका ओळखली जाते आणि त्यानुसार " +
    "डॅशबोर्ड आपोआप उघडतो.",

  /* ---- नोंदणी पृष्ठ ---- */
  "register.eyebrow": "खाते तयार करा",
  "register.hero.title1": "सहभागी व्हा",
  "register.hero.titleAccent": "NyayMitra.",
  "register.hero.copy":
    "खटला शोध, वेळापत्रक, न्यायालयीन आदेश, अनुवाद " +
    "आणि प्रमाणित वकीलांशी संवादासाठी एक नागरिक " +
    "खाते — किंवा त्या संवादांची बाजू घेण्यासाठी " +
    "वकील म्हणून नोंदणी करा.",
  "register.backToSignIn": "← साइन इनकडे परत",
  "register.choice.label": "खात्याचा प्रकार",
  "register.choice.heading": "तुम्ही NyayMitra कसे वापरणार?",
  "register.choice.sub": "तुम्हाला तयार करायचे खाते निवडा.",
  "register.door.citizen.role": "नागरिक",
  "register.door.citizen.title": "वापरकर्ता खाते तयार करा",
  "register.door.citizen.desc":
    "खटले शोधा व जतन करा, न्यायालयीन आदेश वाचा, " +
    "अनुवाद करा आणि प्रमाणित वकीलांशी गप्पा मांडा.",
  "register.door.advocate.role": "वकील",
  "register.door.advocate.title": "वकील खाते तयार करा",
  "register.door.advocate.desc":
    "तुमच्या परवाना आणि व्यावसायिक क्षेत्रांसह " +
    "नोंदणी करा. वापरकर्त्यांकडून गप्पा मिळण्यापूर्वी " +
    "तुमची नोंदणी पडताळली जाते.",
  "register.signInLink": "आधीच खाते आहे? साइन इन करा →",
  "register.submitted.label": "वकील",
  "register.submitted.heading": "नोंदणी सबमिट केली",
  "register.submitted.status":
    "तुमची वकील नोंदणी प्रशासकाच्या पडताळणीच्या " +
    "प्रतीक्षेत आहे.",
  "register.submitted.copy":
    "प्रशासक तुमचा परवाना दस्तऐवज आणि संप्रदाय " +
    "तपासेल. तुमच्या खात्याला मान्यता मिळेपर्यंत " +
    "प्रमाणित वकील सुविधा — वापरकर्त्यांकडून गप्पा " +
    "मिळवणे यासह — बंद राहतात. स्थिती तपासण्यासाठी " +
    "तुम्ही कधीही ईमेल आणि पासवर्डने साइन इन करू शकता.",
  "register.submitted.go": "साइन इनकडे जा",
  "register.chooseType": "← खात्याचा प्रकार निवडा",
  "register.citizen.label": "नागरिक",
  "register.citizen.heading": "तुमचे खाते तयार करा",
  "register.citizen.sub":
    "तुमची भूमिका ठरवलेली आहे — साइन-इनवर ती " +
    "आपोआप ओळखली जाते.",
  "register.field.fullName": "पूर्ण नाव",
  "register.field.namePlaceholder.user": "उदा. आशा वर्मा",
  "register.field.email": "ईमेल",
  "register.field.emailPlaceholder": "you@example.com",
  "register.field.confirm": "पासवर्ड पक्का करा",
  "register.field.confirmPlaceholder": "पासवर्ड पुन्हा टाका",
  "register.field.passwordPlaceholder": "किमान ८ अक्षरे",
  "register.submit.creating": "तुमचे खाते तयार करत आहे...",
  "register.submit.create": "खाते तयार करा",
  "register.lawyer.label": "वकील",
  "register.lawyer.heading": "वकील म्हणून नोंदणी करा",
  "register.lawyer.sub":
    "तुमची नोंदणी प्रतीक्षेत सुरू होते — वापरकर्त्यांकडून " +
    "गप्पा मिळण्यापूर्वी प्रशासक तुमचा परवाना " +
    "पडताळतो.",
  "register.field.namePlaceholder.lawyer": "उदा. वकील प्रिया शर्मा",
  "register.field.lawEmailPlaceholder": "advocate@example.com",
  "register.field.license": "परवाना / बार काउन्सिल नोंदणी आयडी",
  "register.field.licensePlaceholder": "उदा. MAH/1234/2020",
  "register.field.practiceAreas": "व्यावसायिक क्षेत्रे",
  "register.field.practicePlaceholder":
    "उदा. अपराध शास्त्र, कुटुंब शास्त्र",
  "register.field.practiceHint":
    "प्रत्येक क्षेत्र दाण्याने विभागा.",
  "register.optional.heading": "इतर प्रोफाइल माहिती",
  "register.optional.badge": "ऐच्छिक",
  "register.field.barCouncil": "बार काउन्सिल",
  "register.field.barCouncilPlaceholder":
    "उदा. महाराष्ट्र बार काउन्सिल",
  "register.field.years": "अनुभवाची वर्षे",
  "register.field.yearsPlaceholder": "उदा. 7",
  "register.field.phone": "फोन",
  "register.field.bio": "अल्प परिचय",
  "register.field.bioPlaceholder":
    "तुमच्या प्रॅक्टिसबद्दल एक ओळ (ऐच्छिक)",
  "register.field.document": "परवाना / नोंदणी दस्तऐवज",
  "register.field.documentHint":
    "PDF, JPG किंवा PNG — 10 MB पर्यंत. नोंदणी " +
    "पडताळणीदरम्यान प्रशासक या दस्तऐवजाची तपासणी " +
    "करतो.",
  "register.field.photo": "प्रोफाइल फोटो (ऐच्छिक)",
  "register.field.photoHint":
    "JPG, PNG किंवा WebP — 2 MB पर्यंत. सर्व्हर-साइड " +
    "फोटो संग्रह सुरू होईपर्यंत हा फोटो या " +
    "उपकरणावर जतन होतो आणि तुमच्या प्रोफाइलवर " +
    "दिसतो.",
  "register.photo.alt": "प्रोफाइल फोटो पूर्वदृश्य",
  "register.note.retry":
    "तुमचे खाते तयार झाले — पुन्हा सबमिट केल्यावर " +
    "फक्त दस्तऐवज अपलोड पुन्हा प्रयत्न होतो.",
  "register.submit.submitting": "नोंदणी सबमिट करत आहे...",
  "register.submit.retry": "दस्तऐवज अपलोड पुन्हा प्रयत्न करा",
  "register.submit.lawyer": "वकील नोंदणी सबमिट करा",
  "register.err.name": "कृपया तुमचे पूर्ण नाव टाका.",
  "register.err.email": "कृपया वैध ईमेल पत्ता टाका.",
  "register.err.passwordLength":
    "पासवर्ड किमान {n} अक्षरांचे असावे.",
  "register.err.passwordMatch": "पासवर्ड जुळत नाहीत.",
  "register.err.license":
    "कृपया परवाना किंवा नोंदणी क्रमांक टाका.",
  "register.err.practiceMin":
    "किमान एक व्यावसायिक क्षेत्र नमूद करा.",
  "register.err.practiceMax":
    "जास्तीत जास्त {n} व्यावसायिक क्षेत्रे नमूद करा.",
  "register.err.practiceLength":
    "प्रत्येक व्यावसायिक क्षेत्र {n} किंवा त्यापेक्षा " +
    "कमी अक्षरांचे असावे.",
  "register.err.barCouncil":
    "बार काउन्सिल {n} किंवा त्यापेक्षा कमी अक्षरांची " +
    "असावी.",
  "register.err.years":
    "अनुभवाची वर्षे 0 ते {n} या मर्यादेत असावी.",
  "register.err.phone": "कृपया वैध फोन क्रमांक टाका.",
  "register.err.bio":
    "अल्प परिचय {n} किंवा त्यापेक्षा कमी अक्षरांचा असावा.",
  "register.err.documentMissing":
    "तुमचा परवाना किंवा नोंदणी दस्तऐवज जोडा " +
    "(PDF, JPG किंवा PNG).",
  "register.err.documentType":
    "PDF, JPG किंवा PNG फाइल अपलोड करा.",
  "register.err.documentSize":
    "फाइल खूप मोठी आहे. कमाल परवानगी 10 MB आहे.",
  "register.err.photoType":
    "JPG, PNG किंवा WebP प्रतिमा अपलोड करा.",
  "register.err.photoSize":
    "फोटो खूप मोठा आहे. कमाल परवानगी 2 MB आहे.",
  "register.err.photoRead":
    "प्रतिमा वाचता आली नाही. दुसरी फाइल वापरून पहा.",
  "register.err.genericUser":
    "खाते तयार करता आले नाही. कृपया पुन्हा प्रयत्न करा.",
  "register.err.genericLawyer":
    "नोंदणी सबमिट करता आली नाही. कृपया पुन्हा प्रयत्न करा.",

  /* ---- सामायिक नेव्हिगेशन ---- */
  "nav.main": "मुख्य नेव्हिगेशन",
  "nav.brandTagline": "कायदेशीर मदत",
  "nav.home": "मुख्य पृष्ठ",
  "nav.myCases": "माझी खटले",
  "nav.findLawyer": "वकील शोधा",
  "nav.chat": "गप्पा",

  /* ---- मुख्य पृष्ठ ---- */
  "home.eyebrow": "तुमचा कायदेशीर सोबती",
  "home.title1": "तुमचा कायदेशीर प्रवास,",
  "home.titleAccent": "सोपा.",
  "home.copy":
    "तुमचे खटले समजून घ्या, विश्वसनीय कायदेशीर " +
    "व्यावसायिक शोधा, दस्तऐवज अनुवादित करा आणि " +
    "स्पष्ट मार्गदर्शन मिळवा — सर्व एकाच ठिकाणी.",
  "home.ctaExplore": "माझी खटले पाहा",
  "home.servicesLabel": "कायदेशीर सेवा",
  "home.servicesHeading": "तुमच्या कायदेशीर प्रवासाला लागणारे सर्व काही.",
  "home.tile.cases.label": "खटला सेवा",
  "home.tile.cases.desc":
    "तुमचे खटले, तक्रारी आणि खटल्याची स्थिती शोधा व ट्रॅक करा.",
  "home.tile.lawyer.label": "कायदेशीर व्यावसायिक",
  "home.tile.lawyer.desc":
    "संप्रदाय, अनुभव आणि स्थानानुसार वकील शोधा.",
  "home.tile.chat.label": "संदेश",
  "home.tile.chat.desc":
    "तुमच्याशी संपर्क साधलेल्या वकीलाशी किंवा तुमचे खाते " +
    "सांभाळणाऱ्या कर्मचारीशी संभाषण सुरू ठेवा.",
  "home.tile.orders.label": "न्यायालयीन दस्तऐवज",
  "home.tile.orders.title": "न्यायालयीन आदेश",
  "home.tile.orders.desc":
    "न्यायालयीन आदेश वाचा आणि महत्त्वाचे कायदेशीर " +
    "दस्तऐवज समजून घ्या.",
  "home.tile.translate.label": "भाषा सहाय्य",
  "home.tile.translate.title": "अनुवाद",
  "home.tile.translate.desc":
    "कायदेशीर सामग्री सोप्या व परिचयात्मक भाषांमध्ये अनुवादित करा.",
  "home.tile.delay.label": "खटला अंतर्दृष्टी",
  "home.tile.delay.title": "विलंबविश्लेषण",
  "home.tile.delay.desc":
    "खटला उशिरा चालण्याची शक्य कारणे समजून घ्या आणि " +
    "उपयुक्त माहिती मिळवा.",
  "home.tile.voice.label": "आम्हाला सांगा काय घडले",
  "home.tile.voice.title": "आवाज सहाय्य",
  "home.tile.voice.desc":
    "घटनेचे वर्णन आवाजाने किंवा मजकूराने द्या, किंवा तुमच्या " +
    "खटल्यात काय घडले आणि पुढे काय करायचे ते विचारा.",
  "home.tile.timeline.label": "खटला इतिहास",
  "home.tile.timeline.title": "खटला कालक्रम",
  "home.tile.timeline.desc":
    "तुमच्या खटला प्रवासातील महत्त्वाच्या तक्रारी, घटना आणि " +
    "टप्पे ट्रॅक करा.",
  "home.helpsLabel": "न्यायमित्र कसा मदत करतो",
  "home.helpsHeading": "स्पष्ट मार्गदर्शन. आत्मविश्वासू निर्णय.",
  "home.info.understand.title": "समजून घ्या",
  "home.info.understand.desc":
    "कायदेशीर संज्ञा, प्रक्रिया आणि तुमचे हक्क सोप्या भाषेत " +
    "समजावून सांगतो.",
  "home.info.help.title": "विश्वसनीय मदत शोधा",
  "home.info.help.desc":
    "प्रमाणित वकीलांशी जोडा आणि तुमच्यासाठी योग्य " +
    "कायदेशीर मदत मिळवा.",
  "home.info.translate.title": "अनुवाद करा",
  "home.info.translate.desc":
    "कायदेशीर दस्तऐवजांना आत्मविश्वासाने सोप्या भाषेत अनुवाद करा.",
  "home.trust.secure.title": "सुरक्षित आणि गोपनीय",
  "home.trust.secure.desc":
    "तुमचा डेटा एन्क्रिप्ट केलेला आहे आणि नेहमी सुरक्षित आहे.",
  "home.trust.verified.title": "प्रमाणित व्यावसायिक",
  "home.trust.verified.desc":
    "तुमच्यावर विश्वास ठेवू शकणारे वकील, तुम्हाला मिळणार्या " +
    "निकालांसाठी.",
  "home.trust.support.title": "इथे मदतीसाठी",
  "home.trust.support.desc":
    "आम्ही प्रत्येक टप्प्यावर तुमची मदत करण्यासाठी इथे आहोत.",
  "home.ctaLabel": "कायदेशीर मदत लागली आहे?",
  "home.ctaHeading": "तुमच्या खटल्यापासून सुरुवात करा.",
  "home.ctaCopy":
    "तुमच्या खटल्याची माहिती शोधा आणि उपलब्ध न्यायमित्र " +
    "सेवा पाहा.",
  "trans.lang.mr": "मराठी",
  "trans.lang.hi": "हिंदी",
  "trans.lang.en": "इंग्रजी",
  "trans.err.translate":
    "अनुवाद करता आला नाही. कृपया NyayMitra अनुवाद सेवा चालू आहे " +
    "याची खात्री करा.",
  "trans.err.simplify":
    "सोपे करून अनुवाद करता आले नाही. कृपया NyayMitra अनुवाद सेवा " +
    "चालू आहे याची खात्री करा.",
  "trans.note.copy":
    "अनुवादाचा उद्देश कायदेशीर माहितीचे अधिक समजणे वाढवणे आहे. अनुवादित " +
    "मजकूर मूळ कायदेशीर दस्तऐवजाच्या जागी घेऊन येऊ नये.",
  "trans.note.important": "महत्त्वाचे:",
  "trans.example.updates.desc": "महत्त्वाची खटला माहिती समजून घ्या",
  "trans.example.updates.title": "खटल्याची अद्ययावती",
  "trans.example.notices.desc": "औपचारिक कायदेशीर संदेशाचा अनुवाद करा",
  "trans.example.notices.title": "कायदेशीर सूचना",
  "trans.example.orders.desc": "न्यायालयाने दिलेल्या निर्देशांचा अर्थ समजून घ्या",
  "trans.example.orders.title": "न्यायालयीन आदेश",
  "trans.quick.heading": "तुम्ही काय अनुवादित करू शकता?",
  "trans.quick.label": "झटपट सुरुवात",
  "trans.demo.line4.note": "दिनांक ठरवला",
  "trans.demo.line4.label": "तक्रारीसाठी नोंदवला",
  "trans.demo.line3.note": "अर्ज पूर्ण झाला",
  "trans.demo.line3.label": "निपटावला",
  "trans.demo.line2.note": "हर्जान्तदारास नोंद करण्यास सांगितले",
  "trans.demo.line2.label": "उत्तरदेण्याचा आदेश",
  "trans.demo.line1.note": "तक्रार पुढे सरकवली",
  "trans.demo.line1.label": "स्थगित",
  "trans.demo.note":
    "ही सरलीकरण पाइपलाइन चाचणीसाठी बनवलेली नमुना वाक्ये आहेत. ही " +
    "कोणत्याही वास्तव खटल्यातील उतारे नाहीत आणि यात कोणताही वास्तव " +
    "पक्ष, दिनांक किंवा आदेश दर्शवलेला नाही.",
  "trans.demo.heading": "विकासासाठी लिहिलेली चार ओळी",
  "trans.demo.label": "डेमो उदाहरणे · वास्तव आदेश नाहीत",
  "trans.action.again": "पुन्हा सुरू करा",
  "trans.action.translate": "मजकूर अनुवाद करा",
  "trans.busy.pleaseWait":
    "NyayMitra कायदेशीर मजकूर प्रक्रिया करत असताना कृपया प्रतीक्षा करा.",
  "trans.busy.working": "काम सुरू आहे...",
  "trans.busy.translating": "अनुवाद करत आहे...",
  "trans.busy.simplifying": "सोपे करून अनुवाद करत आहे...",
  "trans.output.footer": "NyayMitra भाषा सहाय्य",
  "trans.output.emptyDirectHint":
    "डावीकडे कायदेशीर मजकूर टाका आणि “मजकूर अनुवाद करा” क्लिक करा.",
  "trans.output.emptyDirect": "तुमचा अनुवाद इथे दिसेल",
  "trans.output.emptySimplifyHint":
    "डावीकडे कायदेशीर मजकूर टाका आणि “सोपे करा आणि अनुवाद करा” क्लिक करा.",
  "trans.output.emptySimplify": "तुमचे तीन टप्पे इथे दिसतील",
  "trans.output.copied": "कॉपी केले",
  "trans.output.copy": "कॉपी करा",
  "trans.output.labelDirect": "अनुवादित मजकूर",
  "trans.output.labelSimplify": "मूळ · सोपे · अनुवादित",
  "trans.editor.footer": "कायदेशीर दस्तऐवजाचा अनुवाद",
  "trans.editor.chars": "{n} अक्षरे",
  "trans.editor.placeholder":
    "तुमचा न्यायालयीन आदेश, सूचना, निर्णय किंवा कायदेशीर मजकूर इथे चिकटवा...",
  "trans.editor.clear": "साफ करा",
  "trans.editor.sourceLabel": "तुमचा कायदेशीर मजकूर",
  "trans.swap.disabled":
    "इंग्रजी केवळ स्रोत भाषा म्हणून वापरता येते — ही सेवा हिंदीत " +
    "किंवा मराठीत अनुवाद करते.",
  "trans.swap.title": "भाषा बदला",
  "trans.targetLabel": "अनुवाद या भाषेत",
  "trans.sourceLabel": "स्रोत भाषा",
  "trans.step3": "तिसरा टप्पा",
  "trans.mode.simplify": "कायदेशीर सरलीकरण",
  "trans.mode.direct": "थेट अनुवाद",
  "trans.pill.legal": "कायदेशीर मजकूर",
  "trans.pill.marathi": "मराठी",
  "trans.pill.hindi": "हिंदी",
  "trans.hero.copy":
    "कठीण कायदेशीर भाषा सोप्या समजणीसाठी हिंदीत किंवा मराठीत अनुवाद करा.",
  "trans.hero.titleAccent": "तुमच्या भाषेत",
  "trans.hero.title1": "कायदा समजून घ्या",
  "trans.hero.badge": "NYAYMITRA भाषा सहाय्य",
  "trans.backToDashboard": "← डॅशबोर्डकडे परत",
  "orders.err.simplify": "मजकूर सोपा करून अनुवाद करता आला नाही.",
  "orders.err.lang": "असमर्थित भाषा निवडली आहे.",
  "orders.err.file": "आदेश नोंदवला गेला नाही.",
  "orders.err.explain": "आदेश समजावून सांगता आला नाही.",
  "orders.close": "स्पष्टीकरण बंद करा",
  "orders.dates.label": "या आदेशातील दिनांक",
  "orders.terms.label": "वापरलेले शब्द, सोप्या शब्दांत",
  "orders.section.absent": "दस्तऐवजात उपलब्ध नाही.",
  "orders.section.missing": "या दस्तऐवजात नाही",
  "orders.simplify.sectionLabel": "सोपे करा आणि अनुवाद करा",
  "orders.simplify.again": "पुन्हा चालवा",
  "orders.simplify.working": "काम सुरू आहे…",
  "orders.simplify.intro":
    "मूळ शब्दप्रयोग → सोपी इंग्रजी → खाली निवडलेल्या भाषेत ती सोपी " +
    "इंग्रजी.",
  "orders.simplify.title": "हा आदेश समजून घ्या",
  "orders.simplify.running": "तीन टप्पे काढत आहे…",
  "orders.simplify.step3": "तिसरा टप्पा",
  "orders.layers.noRewording":
    "या उताऱ्यासाठी अधिक सोपा शब्दप्रयोग आढळला नाही, त्यामुळे तो जसा " +
    "आहे तसाच दाखवला जातो.",
  "orders.layer.translated": "3 · {target}, सोप्या इंग्रजीतून",
  "orders.layer.simple": "2 · सोपी इंग्रजी",
  "orders.layer.legal": "1 · मूळ कायदेशीर मजकूर",
  "orders.badge.explainedIn": "{label} भाषेत समजावला",
  "orders.badge.scan": "सुरक्षातपासणी: {status}",
  "orders.badge.ocr": "OCR द्वारे वाचलेला मजकूर",
  "orders.badge.pages": "पृष्ठे",
  "orders.badge.page": "पृष्ठ",
  "orders.paste.submit": "सोप्या शब्दांत समजावून सांगा",
  "orders.paste.placeholder": "न्यायालयीन आदेशाचा मजकूर चिकटवा…",
  "orders.paste.note":
    "फाइल वाचली नाही, त्यामुळे त्यातून सारांश तयार करण्यासाठी अद्याप " +
    "काही नाही. खाली आदेशाचा मजकूर चिकटवा — तो तीन टप्प्यांत दिसेल: " +
    "जसा लिहिलेला आहे, सोप्या इंग्रजीत, आणि वर निवडलेल्या भाषेत.",
  "orders.card.remove": "या खटल्यावरून काढा",
  "orders.card.explain": "हा आदेश समजावून सांगा",
  "orders.card.reading": "आदेश वाचत आहे…",
  "orders.card.uploaded": "अपलोड दिनांक",
  "orders.card.size": "आकार",
  "orders.card.recordOnly": "फक्त नोंद",
  "orders.card.available": "उपलब्ध",
  "orders.case.empty":
    "या खटल्यासाठी अद्याप कोणताही न्यायालयीन आदेश अपलोड केलेला नाही.",
  "orders.case.countMany": "आदेश",
  "orders.case.countOne": "आदेश",
  "orders.case.nextHearing": "पुढील तक्रार दिनांक {date}",
  "orders.empty.copy":
    "न्यायालयीन आदेश खटल्याविरुद्ध जारी केले जातात. माझी खटले यात CNR " +
    "शोधा, खटला जतन करा, आणि त्या खटल्याचे आदेश इथे दिसतील.",
  "orders.empty.heading": "या खात्यावर जतन केलेले खटले नाहीत",
  "orders.list.unit": "आदेश",
  "orders.list.heading": "खटल्यानुसार न्यायालयीन आदेश",
  "orders.list.label": "तुमचे दस्तऐवज",
  "orders.upload.submit": "अपलोड करा आणि समजावून सांगा",
  "orders.upload.reading": "वाचत आहे…",
  "orders.upload.chooseFile": "फाइल निवडा",
  "orders.upload.langAria": "स्पष्टीकरणासाठी भाषा",
  "orders.upload.noCases": "जतन केलेले खटले नाहीत",
  "orders.upload.caseAria": "हा आदेश ज्या खटल्याचा आहे तो खटला",
  "orders.upload.desc":
    "हा आदेश कोणत्या खटल्याचा आहे तो निवडा, मग फाइल — PDF किंवा " +
    "प्रतिमा. ती त्याच खटल्यावर जतन होते आणि तीन टप्प्यांत समजावला " +
    "जातो: जसा तो लिहिलेला आहे तसाच आदेश, तेच शब्द सोप्या इंग्रजीत, " +
    "आणि ती सोपी इंग्रजी हिंदीत किंवा मराठीत — खाली कोणती भाषा " +
    "निवडता ती.",
  "orders.upload.heading": "न्यायालयीन आदेश समजावून सांगा",
  "orders.hero.copy":
    "जो आदेश कोणत्या खटल्याशी संबंधित आहे तो त्या खटल्यावर अपलोड करा — " +
    "NyayMitra तो तुम्हाला सोप्या भाषेत परत सांगेल, खटल्यानुसार वेगळा " +
    "करून, जशा तुमचा वकील तो नोंदवणार.",
  "orders.hero.titleAccent": "तुमचे न्यायालयीन आदेश",
  "orders.hero.title1": "शोधा आणि समजून घ्या",
  "orders.hero.badge": "NYAYMITRA न्यायालय सेवा",
  "orders.backToDashboard": "← डॅशबोर्डकडे परत",
  "explainer.urgency": "या टप्प्यासाठी तातडी: {level}",
  "explainer.whatNext": "पुढे काय करावे",
  "explainer.whereStage": "तुमचा खटला जिथे आहे: {stage}",
  "explainer.error": "आत्ता पुढील पायरी काढता आली नाही.",
  "explainer.nextStep": "पुढील पायरी समजावून सांगा",
  "explainer.shown": "पुढील पायरी दाखवली",
  "explainer.working": "समजून घेत आहे…",
  "explainer.stop": "थांबवा ▪",
  "explainer.listen": "ऐका",
  "explainer.copied": "कॉपी केले",
  "explainer.copy": "कॉपी करा",
  "explainer.glossary": "या मजकूरातील कायदेशीर शब्दकोशातील शब्द",
  "explainer.englishDone":
    "इंग्रजी मागितली असल्याने दुसरा टप्पाच हा अंतिम उत्तर आहे.",
  "explainer.noPlainer":
    "या उताऱ्यासाठी अधिक सोपी शब्दरचना आढळली नाही, म्हणून ती " +
    "लिखाप्रमाणे दाखवली जात आहे.",
  "explainer.layer3": "३ · सोप्या इंग्रजीतून {lang}",
  "explainer.layer2": "२ · सोपी इंग्रजी",
  "explainer.layer1": "१ · मूळ कायदेशीर मजकूर",
  "explainer.step3": "{lang} मध्ये टप्पा ३",
  "explainer.title": "कायदेशीर आदेश स्पष्टीकरण",
  "explainer.lang.english": "इंग्रजी",
  "explainer.lang.hindi": "हिंदी",
  "explainer.lang.marathi": "मराठी",
  "ongoing.working": "प्रक्रिया सुरू आहे…",
  "ongoing.versus": "बनाम",
  "ongoing.nextHearing": "पुढील तक्रारी {date}",
  "ongoing.held": "झाली {date}",
  "ongoing.today": "आज, {date}",
  "ongoing.dateNotSet": "तारीख ठरवलेली नाही",
  "docs.retry": "पुन्हा प्रयत्न करा",
  "docs.error": "आत्ता न्यायालयीन कागदपत्रे लोड करता आली नाहीत.",
  "docs.forbidden": "या खटल्याच्या दस्तऐवजांमध्ये तुमचा प्रवेश नाही.",
  "docs.signedOut":
    "या खटल्याची न्यायालयीन कागदपत्रे पाहण्यासाठी पुन्हा साइन इन करा.",
  "docs.unavailableNote":
    "दस्तऐवज सेवा हा खटला ओळखत नाही — काहीही लपवलेले नाही; " +
    "आत्ता इथे दाखवण्यासाठी फक्त काहीच नाही.",
  "docs.unavailable":
    "अद्याप या खटल्यासाठी न्यायालयीन कागदपत्रे उपलब्ध नाहीत.",
  "docs.empty": "अद्याप या खटल्यासाठी कोणतीही न्यायालयीन कागदपत्रे प्रकाशित केलेली नाहीत.",
  "docs.noDownloadTitle": "बॅकएंडने डाउनलोड करण्यायोग्य फाइल दिली नाही",
  "docs.downloadUnavailable": "डाउनलोड उपलब्ध नाही",
  "docs.download": "डाउनलोड",
  "docs.noViewTitle": "बॅकएंडने पहण्यायोग्य फाइल दिली नाही",
  "docs.viewUnavailable": "पहणे उपलब्ध नाही",
  "docs.view": "पहा",
  "docs.loading": "न्यायालयीन कागदपत्रे मागवत आहे…",
  "docs.demoBody":
    "या वातावरणात दस्तऐवज एपीआय जोडलेले नसल्यामुळे नमुना ओळी " +
    "दाखवल्या जात आहेत — हे खरे न्यायालयीन कागदपत्र नाहीत आणि " +
    "ती कुठेही जात नाहीत.",
  "docs.demoStrong": "विकास डेमो डेटा.",
  "docs.demoChip": "डेमो",
  "docs.demoChipTitle": "फक्त विकासासाठी नमुना रेकॉर्ड",
  "docs.copy":
    "खटला सेवेद्वारे या खटल्यासाठी प्रकाशित केलेले आदेश, " +
    "सूचना आणि निर्णय — जेव्हा बॅकएंड ते पुरवतो तेव्हाच " +
    "यादीत.",
  "docs.title": "न्यायालयीन कागदपत्रे",
  "detail.cat.other": "इतर",
  "detail.cat.correspondence": "पत्रव्यवहार",
  "detail.cat.courtOrder": "न्यायालयीन आदेश",
  "detail.cat.identity": "ओळख",
  "detail.cat.evidence": "साक्षे",
  "detail.cat.filing": "दाखल",
  "detail.doc.open": "उघडा",
  "detail.doc.remove": "काढून टाका",
  "detail.doc.recordOnly": "फक्त नोंद",
  "detail.doc.preview": "पूर्वदृश्य",
  "detail.doc.hide": "लपवा",
  "detail.timeline.empty":
    "अद्याप या खटल्यासाठी कोणतीही घटना नोंदवलेली नाही.",
  "detail.timeline.noDate": "तारीख नोंदवलेली नाही",
  "detail.timeline.introHistory":
    "या खटल्यात न्यायालयाने नोंदवलेल्या तक्रारी.",
  "detail.timeline.intro":
    "जुन्यापासून नवीनकडे, फक्त रेकॉर्डमध्ये असलेल्या तारखांवर " +
    "आधारित.",
  "detail.timeline.history": "तक्रारींचा इतिहास",
  "detail.timeline.title": "खटला कालक्रम",
  "detail.orders.explain": "हा आदेश समजावून सांगा",
  "detail.orders.no": "आदेश क्रमांक {n}",
  "detail.orders.empty":
    "अद्याप या खटल्याविषयी कोणताही आदेश नोंदवलेला नाही.",
  "detail.orders.copy":
    "या खटल्यात न्यायालयाने नोंदवलेले — डॉकेट नोंद, " +
    "आदेशाची प्रत नाही.",
  "detail.orders.title": "पारित आदेश",
  "detail.docs.empty": "या खटल्यात अद्याप कोणतेही कागदपत्र जोडलेले नाहीत.",
  "detail.docs.add": "＋ कागदपत्रे जोडा",
  "detail.docs.uploading": "अपलोड होत आहे…",
  "detail.docs.categoryAria": "दस्तऐवजाचा प्रकार",
  "detail.docs.copy":
    "या खटल्यात जोडलेले सर्व काही. नियुक्त वकीलाला " +
    "हीच यादी दिसते.",
  "detail.docs.title": "खटल्याची कागदपत्रे",
  "detail.guidance.error":
    "आत्ता मार्गदर्शन मिळवता आले नाही. काही क्षणांनी पुन्हा प्रयत्न करा.",
  "detail.guidance.ask": "मी पुढे काय करावं?",
  "detail.guidance.asking": "विचारत आहे…",
  "detail.daysAtStage": "या टप्प्यावर दिवस",
  "detail.respondent.other": "उत्तरदार",
  "detail.respondent.one": "उत्तरदार",
  "detail.daysOnFile": "फाइलवर दिवस",
  "detail.registrationDate": "नोंदणी तारीख",
  "detail.firstHearing": "पहिली तक्रारी",
  "detail.schedule": "वेळापत्रक",
  "detail.filingNumber": "दाखल क्रमांक",
  "detail.notListed": "अद्याप नमूद नाही",
  "detail.presidingJudge": "अध्यक्षत करणारे न्यायाधीश",
  "detail.district": "जिल्हा",
  "detail.court": "न्यायालय",
  "detail.section": ", कलम {n}",
  "detail.actApplied": "लागू कायदा",
  "detail.petAdvocate": "विनयकर्त्याचा वकील",
  "detail.parties": "बाजू",
  "detail.source.dev": "विकास डेटा",
  "detail.source.live": "थेट न्यायालयीन माहिती",
  "detail.assignedAdvocate": "नियुक्त वकील",
  "detail.chat": "नियुक्त वकीलाशी गप्पा",
  "search.empty.noneBody":
    "त्या शोधाशी जुळणारा कोणताही खटला आढळला नाही. वेगळा " +
    "सीएनआर क्रमांक, विनयकर्त्याचे नाव किंवा खटल्याचा प्रकार " +
    "वापरून पहा.",
  "search.empty.noneTitle": "कोणताही खटला सापडला नाही",
  "search.empty.savedBody":
    "वरील चौकटीत सीएनआर क्रमांकाने विद्यमान खटला शोधा, आणि " +
    "नंतर तो इथे ट्रॅक करण्यासाठी \"माझ्या खटल्यांमध्ये जतन " +
    "करा\" निवडा — कागदपत्रे, तक्रारी आणि आदेश खटल्यासोबत जातात.",
  "search.empty.savedTitle": "अजून जतन केलेले खटले नाहीत",
  "search.noFilter": "फक्त तुम्ही ट्रॅक करण्यासाठी जतन केलेले खटले दाखवले जातात",
  "search.showing": "\"{q}\" शी जुळणारे तुमचे जतन केलेले खटले दाखवत आहे",
  "search.saved.filtered": "{total} पैकी {shown} जतन केलेले खटले",
  "search.saved.other": "{n} जतन केलेले खटले",
  "search.saved.one": "{n} जतन केलेला खटला",
  "search.allTypes": "सर्व खटल्याचे प्रकार",
  "search.clear": "शोध मेटवा",
  "search.placeholder": "सीएनआर, विनयकर्ता, खटल्याच्या प्रकाराने शोधा...",
  "cnr.open": "संपूर्ण खटला उघडा",
  "cnr.saved": "माझ्या खटल्यांमध्ये जतन केले",
  "cnr.save": "माझ्या खटल्यांमध्ये जतन करा",
  "cnr.orders.other": "{n} आदेश पारित झाले आहेत",
  "cnr.orders.one": "{n} आदेश पारित झाला आहे",
  "cnr.hearings.other": "{n} तक्रारी नोंदवली आहेत",
  "cnr.hearings.one": "{n} तक्रारी नोंदवली आहे",
  "cnr.submit": "खटला शोधा",
  "cnr.busy": "शोधत आहे…",
  "cnr.err.notFound": "हा सीएनआर शोधता आला नाही.",
  "cnr.err.offline":
    "खटला सेवा पोहोचता आली नाही. काही क्षणांनी पुन्हा प्रयत्न करा.",
  "cnr.err.malformed": "हा सीएनआर नाही. {hint}",
  "cnr.err.empty": "तुम्ही उघडू इच्छित असलेल्या खटल्याचा सीएनआर टाका.",
  "cnr.hintFormat": "आधी चार अक्षरे आणि नंतर बारा अंक, जसे {example}.",
  "cnr.hintLong": "सीएनआर १६ अक्षरांचा असतो — {n} अक्षरे जास्त आहेत.",
  "cnr.hintShort": "सीएनआर १६ अक्षरांचा असतो — अजून {n} अक्षरे बाकी.",
  "cnr.hintEmpty": "शोधण्यासाठी सीएनआर टाका — उदा. {example}.",
  "cnr.inputLabel": "सीएनआर क्रमांक",
  "cnr.intro":
    "प्रत्येक खटल्याला एक १६ अक्षरांचा सीएनआर असतो — " +
    "चार अक्षरे आणि नंतर बारा अंक, सूचना किंवा आदेशपत्र्यावर " +
    "छापल्याप्रमाणे. रेकॉर्ड वाचण्यासाठी इथे उघडतो; तो " +
    "ट्रॅक करण्यासाठी \"माझ्या खटल्यांमध्ये जतन करा\" निवडा.",
  "cnr.heading": "सीएनआर क्रमांकाने शोधा",
  "cnr.label": "खटला शोधा",
  "cases.card.view": "खटला पहा",
  "cases.card.advocate": "वकील:",
  "cases.label.nextHearing": "पुढील तक्रारी",
  "cases.label.court": "न्यायालय",
  "cases.label.respondents": "उत्तरदार",
  "cases.label.petitioner": "विनयकर्ता",
  "cases.label.cnr": "सीएनआर क्रमांक",
  "cases.filed": "दाखल",
  "cases.gone": "हा खटला आता तुमच्या जतन केलेल्या खटल्यांमध्ये नाही.",
  "cases.allCases": "← सर्व खटले",
  "cases.hero.copy":
    "या पृष्ठावर फक्त तुम्ही जतन केलेले खटलेच दिसतात — " +
    "इतर कोणाचेही नाही. सीएनआरने खटला शोधा, तो संपूर्ण " +
    "वाचण्यासाठी उघडा, कागदपत्रे जोडा आणि खटला सांभाळणाऱ्या " +
    "वकीलाशी बोला.",
  "cases.hero.titleAccent": "ट्रॅक करा",
  "cases.hero.title1": "तुमचे खटले",
  "cases.eyebrow": "न्यायमित्र — माझे खटले",
  "cases.backToDashboard": "← डॅशबोर्डकडे परत",
  "chat.error.start": "गप्पा सुरू करता आली नाही.",
  "chat.error.delete": "संभाषण हटवले नाही.",
  "chat.error.send": "संदेश पाठवला नाही.",
  "chat.error.loadLawyers": "प्रमाणित वकील लोड करता आले नाही.",
  "chat.error.openChat": "गप्पा उघडता आली नाही.",
  "chat.error.loadConversations": "संभाषण लोड करता आली नाहीत.",
  "chat.send": "पाठवा",
  "chat.sending": "पाठवत आहे…",
  "chat.composer.aria": "संदेश",
  "chat.composer.placeholder": "{name} ला संदेश लिहा…",
  "chat.thread.empty": "अजून एकही संदेश नाही — नमस्कार करा.",
  "chat.case": "खटला {cnr}",
  "chat.placeholder": "वाचण्यासाठी एक संभाषण निवडा.",
  "chat.picker.empty": "सध्या संदेश पाठवण्यासाठी कोणी नवीन नाही.",
  "chat.picker.title": "संभाषण सुरू करा",
  "chat.delete.confirm": "{name} सोबतचे संभाषण हटवण्याची खात्री करा",
  "chat.delete.label": "{name} सोबतचे संभाषण हटवा",
  "chat.delete.armed": "हटवा",
  "chat.noMessages": "अजून संदेश नाही",
  "chat.you": "तुम: ",
  "chat.role.admin": "प्रशासक",
  "chat.role.staff": "कर्मचारी",
  "chat.role.lawyer": "वकील",
  "chat.role.user": "वापरकर्ता",
  "chat.category.admins": "प्रशासक",
  "chat.category.fromStaff": "कर्मचारींकडून",
  "chat.category.fromLawyers": "वकीलांकडून",
  "chat.category.admin": "प्रशासक",
  "chat.category.staff": "कर्मचारी",
  "chat.category.lawyers": "वकील",
  "chat.category.clients": "ग्राहक",
  "chat.category.all": "सर्व",
  "chat.empty.with": "{who} शी अजून कोणतीही संभाषण नाहीत.",
  "chat.empty.from": "{who} अजून एकही संदेश नाही.",
  "chat.empty.all": "इथे अजून एकही संभाषण नाही.",
  "chat.empty.hint": "खाली संभाषण सुरू करा, किंवा वकील शोधा पृष्ठावरून वकीलाचे प्रोफाइल उघडा आणि “गप्पा” दाबा.",
  "chat.empty.title": "अजून एकही संभाषण नाही.",
  "chat.loading": "संभाषण लोड होत आहेत…",
  "chat.close": "बंद करा",
  "chat.newChat": "＋ नवीन गप्पा",
  "chat.sidebar.title": "संदेश",
  "chat.hero.recordNote": "प्रत्येक संदेश खटल्याच्या नोंदीतच राहतो.",
  "chat.hero.citizen": "नागरिक",
  "chat.hero.canMessage": "{role} म्हणून, तुम्ही यांना संदेश पाठवू शकता: {list}.",
  "chat.titleAccent": "संभाषणे",
  "chat.title1": "तुमची",
  "chat.eyebrow": "NyayMitra संदेश",
  "chat.backToDashboard": "← डॅशबोर्डकडे परत",
  "lawyerProfile.footer": "NyayMitra वरील वकीलांची माहिती कनेक्ट केलेल्या बॅकएंड API द्वारे उपलब्ध करवली जाते.",
  "lawyerProfile.hoursUnavailable": "कार्यालयीन वेळ उपलब्ध नाही",
  "lawyerProfile.hoursLabel": "कार्यालयीन वेळ",
  "lawyerProfile.bioUnavailable": "व्यावसायिक परिचय उपलब्ध नाही.",
  "lawyerProfile.bioLabel": "व्यावसायिक परिचय",
  "lawyerProfile.section.overview": "व्यावसायिक आढावा",
  "lawyerProfile.section.additional": "अतिरिक्त माहिती",
  "lawyerProfile.block.languages": "जाणीवेतील भाषा",
  "lawyerProfile.block.education": "शैक्षणिक पात्रता",
  "lawyerProfile.section.qualifications": "पात्रता",
  "lawyerProfile.section.educationLanguages": "शिक्षण आणि भाषा",
  "lawyerProfile.field.website": "वेबसाइट",
  "lawyerProfile.field.preferredContact": "पसंतीचा संपर्क",
  "lawyerProfile.field.officePhone": "कार्यालयीन फोन",
  "lawyerProfile.field.professionalEmail": "व्यावसायिक ईमेल",
  "lawyerProfile.field.professionalPhone": "व्यावसायिक फोन",
  "lawyerProfile.section.professionalContact": "व्यावसायिक संपर्क",
  "lawyerProfile.section.contact": "संपर्क",
  "lawyerProfile.officeAddressUnavailable": "कार्यालयाचा पत्ता उपलब्ध नाही",
  "lawyerProfile.officeAddressLabel": "कार्यालयाचा पत्ता",
  "lawyerProfile.field.pincode": "पिन कोड",
  "lawyerProfile.field.city": "शहर",
  "lawyerProfile.field.district": "जिल्हा",
  "lawyerProfile.field.state": "राज्य",
  "lawyerProfile.section.professionalLocation": "व्यावसायिक स्थान",
  "lawyerProfile.section.officeLocation": "कार्यालय आणि स्थान",
  "lawyerProfile.block.courtsOfPractice": "प्रॅक्टिस न्यायालये",
  "lawyerProfile.notAvailable": "उपलब्ध नाही",
  "lawyerProfile.block.practiceAreas": "व्यावसायिक क्षेत्रे",
  "lawyerProfile.years": "{n} वर्षे",
  "lawyerProfile.field.yearsOfExperience": "अनुभवाची वर्षे",
  "lawyerProfile.field.yearOfEnrollment": "नोंदणीचे वर्ष",
  "lawyerProfile.field.barCouncil": "बार काउन्सिल",
  "lawyerProfile.field.barId": "बार आयडी / बार कोड",
  "lawyerProfile.field.registrationNumber": "रजिस्ट्रेशन क्रमांक",
  "lawyerProfile.field.enrollmentNumber": "नोंदणी क्रमांक",
  "lawyerProfile.section.legalPractice": "कायदेशीर प्रॅक्टिस",
  "lawyerProfile.section.professional": "व्यावसायिक माहिती",
  "lawyerProfile.field.dob": "जन्मदिनांक",
  "lawyerProfile.field.gender": "लिंग",
  "lawyerProfile.field.fullName": "पूर्ण नाव",
  "lawyerProfile.field.lawyerId": "वकील आयडी",
  "lawyerProfile.section.personal": "वैयक्तिक तपशील",
  "lawyerProfile.section.basic": "मूलभूत माहिती",
  "lawyerProfile.summary.currentStatus": "सध्याची स्थिती",
  "lawyerProfile.summary.profileStatus": "प्रोफाइल स्थिती",
  "lawyerProfile.summary.registrationAuthority": "नोंदणी प्राधिकरण",
  "lawyerProfile.summary.barCouncil": "बार काउन्सिल",
  "lawyerProfile.summary.barEnrollment": "बार नोंदणी",
  "lawyerProfile.summary.enrollmentYear": "नोंदणी वर्ष",
  "lawyerProfile.summary.years": "वर्षे",
  "lawyerProfile.summary.experience": "अनुभव",
  "lawyerProfile.editProfile": "प्रोफाइल दुरुस्त करा",
  "lawyerProfile.record.copy": "खाली दिलेली संपूर्ण माहिती NyayMitra कडे तुमच्याविषयी नोंदवलेली आहे. काही बदलले असेल तर इथे दुरुस्त करा.",
  "lawyerProfile.record.label": "तुमची नोंद",
  "lawyerProfile.locationUnavailable": "स्थान उपलब्ध नाही",
  "lawyerProfile.legalProfessional": "कायदेशीर व्यावसायिक",
  "lawyerProfile.eyebrow": "NyayMitra वकील प्रोफाइल",
  "lawyerProfile.back": "← डॅशबोर्ड",
  "lawyerProfile.edit.field.educationQualifications": "शैक्षणिक पात्रता",
  "lawyerProfile.edit.field.languagesKnown": "जाणीवेतील भाषा",
  "lawyerProfile.edit.field.courtsOfPractice": "प्रॅक्टिस न्यायालये",
  "lawyerProfile.edit.field.practiceAreas": "व्यावसायिक क्षेत्रे",
  "lawyerProfile.edit.field.officeAddress": "कार्यालयाचा पत्ता",
  "lawyerProfile.edit.field.preferredContact": "पसंतीचा संपर्क पद्धत",
  "lawyerProfile.edit.field.officePhone": "कार्यालयीन फोन",
  "lawyerProfile.edit.field.professionalPhone": "व्यावसायिक फोन",
  "lawyerProfile.edit.field.professionalEmail": "व्यावसायिक ईमेल",
  "lawyerProfile.edit.field.workingOfficeHours": "कार्यालयीन वेळ",
  "lawyerProfile.edit.field.professionalBio": "व्यावसायिक परिचय",
  "lawyerProfile.edit.discard": "बदल वगळा",
  "lawyerProfile.edit.save": "बदल जतन करा",
  "lawyerProfile.edit.onePerLine": "प्रत्येक ओळीवर एक नोंद",
  "lawyerProfile.edit.readonlyNote": "नोंदणी क्रमांक, नोंदणी आणि बार काउन्सिल हे काउन्सिलकडे नोंदवलेले आहे. ते संदर्भासाठी दाखवले जाते आणि इथे दुरुस्त करता येत नाहीत.",
  "lawyerProfile.edit.detailsHeading": "जे बदलले आहे ते दुरुस्त करा",
  "lawyerProfile.edit.detailsLabel": "तुमची माहिती",
  "lawyerProfile.edit.note": "दुरुस्त्या याच उपकरणावर जतन होतात आणि तुमचे प्रोफाइल जिथे दिसते तिथे त्याच मुळे दिसतात.",
  "lawyerProfile.edit.eyebrow": "तुमचे प्रोफाइल दुरुस्त करत आहात",
  "lawyerProfile.edit.cancelBack": "← रद्द करा",
  "lawyerProfile.notFound.copy": "API कडून कोणतीही वकील माहिती परत आली नाही.",
  "lawyerProfile.notFound.title": "वकील प्रोफाइल सापडले नाही",
  "lawyerProfile.error.load": "वकील प्रोफाइल लोड करता आले नाही.",
  "lawyerProfile.error.title": "प्रोफाइल लोड करता आले नाही",
  "lawyerProfile.loading.copy": "NyayMitra मधून व्यावसायिक माहिती मिळवत आहे.",
  "lawyerProfile.loading.title": "वकील प्रोफाइल लोड होत आहे...",
  "lawyerProfile.backToDashboard": "← डॅशबोर्डकडे परत",
  "lawyer.pagination.next": "पुढील →",
  "lawyer.pagination.page": "पृष्ठ {page} पैकी {totalPages}",
  "lawyer.pagination.previous": "← मागील",
  "lawyer.card.viewProfile": "प्रोफाइल पहा",
  "lawyer.card.notListed": "सूचीबद्ध नाही",
  "lawyer.card.languages": "भाषा",
  "lawyer.card.enrolled": "नोंदणी",
  "lawyer.card.location": "स्थान",
  "lawyer.card.experience": "अनुभव",
  "lawyer.card.yrs": "{n} वर्षे",
  "lawyer.card.generalPractice": "सर्वसाधारण प्रॅक्टिस",
  "lawyer.card.verified": "प्रमाणित",
  "lawyer.card.senior": "वरिष्ठ वकील",
  "lawyer.empty.clear": "गाळणी हटवा",
  "lawyer.empty.copy": "तुमचा शोध बदलून पहा, किंवा दुसरे व्यावसायिक क्षेत्र किंवा शहर निवडा.",
  "lawyer.empty.title": "कोणतेही वकील सापडले नाहीत",
  "lawyer.error.retry": "पुन्हा प्रयत्न करा",
  "lawyer.error.hint": "पोर्ट 8000 वर FastAPI सेवा सुरू करा आणि नंतर पुन्हा प्रयत्न करा.",
  "lawyer.error.service": "NyayMitra वकील सेवेपर्यंत पोहोचता आले नाही.",
  "lawyer.error.title": "वकील सेवा उपलब्ध नाही",
  "lawyer.results.verified": "प्रमाणित प्रोफाइल",
  "lawyer.results.heading": "तुमच्या कायदेशीर गरजांसाठी वकील",
  "lawyer.results.label": "प्रमाणित वकील",
  "lawyer.filters.reset": "गाळणी रीसेट करा",
  "lawyer.results.showing": "{first}–{last} दाखवत आहे",
  "lawyer.results.found": "वकील आढळले",
  "lawyer.filter.allCities": "सर्व शहरे",
  "lawyer.filter.allPracticeAreas": "सर्व व्यावसायिक क्षेत्रे",
  "lawyer.search.placeholder": "नावाने वकील शोधा...",
  "lawyer.heroCopy": "नाव, व्यावसायिक क्षेत्र व स्थानानुसार प्रमाणित वकील शोधा — ही माहिती NyayMitra च्या वकील नोंदणी यादीतून थेट मिळते.",
  "lawyer.titleAccent": " कायदेशीर तज्ज्ञ.",
  "lawyer.title1": "योग्य",
  "lawyer.eyebrow": "कायदेशीर व्यावसायिक नेटवर्क",
  "lawyer.backToDashboard": "← डॅशबोर्डकडे परत",
};
