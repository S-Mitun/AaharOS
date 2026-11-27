import { STEPS } from "../guide/steps";
import { STEPS_TA } from "../guide/stepsTa";

/**
 * Tamil for every screen. Keys are the English text exactly as a screen shows it (trimmed); the page translator
 * (domTranslate.ts) swaps them while Tamil is on and puts the English back when it is turned off. Numbers, rupee
 * amounts, units such as kg and L, document numbers and DEMO names are never translated. Sentences that carry a
 * number are matched by PATTERNS below.
 */
export const TA: Record<string, string> = {
  // ---------- top bar, menu, footer ----------
  "Sign in": "உள்நுழை",
  "Sign out": "வெளியேறு",
  "Restart tour": "சுற்றுலாவை மீண்டும் தொடங்கு",
  Menu: "பட்டியல்",
  "Skip to content": "உள்ளடக்கத்திற்குச் செல்",
  "AaharOS home": "AaharOS முகப்பு",
  "How to": "எப்படி",
  "How to use AaharOS": "AaharOS-ஐ எப்படிப் பயன்படுத்துவது",
  Guide: "வழிகாட்டி",
  Salesman: "விற்பனையாளர்",
  Admin: "நிர்வாகம்",
  Production: "உற்பத்தி",
  Owner: "உரிமையாளர்",
  Auditor: "தணிக்கையாளர்",
  you: "நீங்கள்",
  "All companies, people, GSTINs and licence numbers in this app are fictional":
    "இந்தச் செயலியில் உள்ள நிறுவனங்கள், நபர்கள், GSTIN மற்றும் உரிம எண்கள் அனைத்தும் கற்பனையான",
  "data.": "தரவு.",
  // ---------- screen names and descriptions ----------
  "Start here": "இங்கே தொடங்கு",
  "Guided tour": "வழிகாட்டும் சுற்றுலா",
  "Sample-day check": "மாதிரி நாள் சரிபார்ப்பு",
  "What AaharOS is, in one page.": "AaharOS என்றால் என்ன, ஒரே பக்கத்தில்.",
  "One working day, one card per step: who, where, what to type, what you should see.":
    "ஒரு வேலை நாள், ஒவ்வொரு படிக்கும் ஓர் அட்டை: யார், எங்கே, என்ன தட்டச்சு செய்ய வேண்டும், என்ன பார்க்க வேண்டும்.",
  "Replay one sample working day on a practice factory and check 26 figures in a minute.":
    "ஒரு மாதிரி வேலை நாளைப் பயிற்சித் தொழிற்சாலையில் மீண்டும் இயக்கி, 26 எண்களை ஒரு நிமிடத்தில் சரிபார்க்கவும்.",
  Today: "இன்று",
  "New order": "புதிய ஆர்டர்",
  "My orders": "என் ஆர்டர்கள்",
  Summary: "சுருக்கம்",
  Freshness: "புத்துணர்ச்சி",
  "Order inbox": "ஆர்டர் பெட்டி",
  "Invoices and dispatch": "விலைப்பட்டியல் மற்றும் அனுப்புதல்",
  Collections: "வசூல்",
  "Trips and cost-to-serve": "பயணங்கள் மற்றும் சேவைச் செலவு",
  Purchases: "கொள்முதல்",
  "Batch card": "தொகுப்பு அட்டை",
  "Run costs": "தொகுப்புச் செலவுகள்",
  "Batch planner": "தொகுப்புத் திட்டமிடல்",
  "Trace and recall": "கண்டறிதல் மற்றும் திரும்பப் பெறுதல்",
  "Oil and fill weights": "எண்ணெய் மற்றும் நிரப்பு எடை",
  "Morning brief": "காலைச் சுருக்கம்",
  "Where profit leaks": "லாபம் எங்கே கசிகிறது",
  Reports: "அறிக்கைகள்",
  Settings: "அமைப்புகள்",
  "Your customers in route order, with one-tap “Repeat last order”.":
    "உங்கள் வாடிக்கையாளர்கள் வழி வரிசையில், ஒரே தட்டலில் “கடைசி ஆர்டரை மீண்டும் செய்”.",
  "Pick a customer, set packets, save. Works with no network.":
    "வாடிக்கையாளரைத் தேர்ந்தெடு, பாக்கெட்டுகளை அமை, சேமி. இணையம் இல்லாமலும் வேலை செய்யும்.",
  "Every order and where it is: saved on phone, received by factory, approved.":
    "ஒவ்வொரு ஆர்டரும் எங்கே உள்ளது: தொலைபேசியில் சேமிக்கப்பட்டது, தொழிற்சாலை பெற்றது, ஒப்புதல் அளிக்கப்பட்டது.",
  "Packets and order value per customer, last 30 days (ordered, not invoiced).":
    "கடந்த 30 நாட்களில் ஒவ்வொரு வாடிக்கையாளருக்குமான பாக்கெட்டுகளும் ஆர்டர் மதிப்பும் (ஆர்டர் செய்யப்பட்டவை, விலைப்பட்டியல் இடப்படாதவை).",
  "Packets that may still be on each customer's shelf, flagged before their best-before (an estimate).":
    "ஒவ்வொரு வாடிக்கையாளரின் அலமாரியிலும் இன்னும் இருக்கக்கூடிய பாக்கெட்டுகள், காலாவதிக்கு முன்பே குறிக்கப்படுகின்றன (ஒரு மதிப்பீடு).",
  "Approve, part-approve or reject orders against available-to-promise stock.":
    "வழங்கக்கூடிய இருப்பைப் பார்த்து ஆர்டர்களை ஒப்புக்கொள், பகுதியாக ஒப்புக்கொள் அல்லது நிராகரி.",
  "GST invoices (CGST + SGST or IGST) and FEFO dispatch, oldest batch first.":
    "GST விலைப்பட்டியல்கள் (CGST + SGST அல்லது IGST) மற்றும் பழைய தொகுப்பு முதலில் என்ற FEFO அனுப்புதல்.",
  "Record payments and see what each customer still owes.":
    "பணம் பெற்றதைப் பதிவு செய்து, ஒவ்வொரு வாடிக்கையாளரும் இன்னும் எவ்வளவு தர வேண்டும் என்று பார்.",
  "Plan delivery trips from the day's dispatches, record actual km, and see each customer's cost-to-serve.":
    "அன்றைய அனுப்புதல்களிலிருந்து விநியோகப் பயணங்களைத் திட்டமிடு, ஓட்டிய கி.மீ.-ஐப் பதிவு செய், ஒவ்வொரு வாடிக்கையாளருக்குமான சேவைச் செலவைப் பார்.",
  "Receive raw materials with the supplier lot; the average cost updates itself.":
    "சப்ளையர் லாட் எண்ணுடன் மூலப்பொருட்களைப் பெறு; சராசரி விலை தானாகவே புதுப்பிக்கப்படும்.",
  "Start a batch, issue materials with a stock preview, record good packets and damage.":
    "தொகுப்பைத் தொடங்கு, இருப்பு முன்னோட்டத்துடன் பொருட்களை வழங்கு, நல்ல பாக்கெட்டுகளையும் சேதத்தையும் பதிவு செய்.",
  "Add labour and gas to a finished batch, see the cost per packet, mark it final.":
    "முடிந்த தொகுப்புக்கு கூலி மற்றும் எரிவாயுச் செலவைச் சேர், ஒரு பாக்கெட்டின் செலவைப் பார், இறுதி எனக் குறி.",
  "How many batches the stock allows, what to make next and what to buy. Creates drafts only.":
    "இருப்பு எத்தனை தொகுப்புகளுக்குப் போதும், அடுத்து என்ன செய்வது, என்ன வாங்குவது. வரைவுகளை மட்டுமே உருவாக்கும்.",
  "Where a batch came from and where every packet went; simulate a recall (DEMO, nothing sent).":
    "ஒரு தொகுப்பு எங்கிருந்து வந்தது, ஒவ்வொரு பாக்கெட்டும் எங்கே சென்றது; திரும்பப் பெறுதலை ஒத்திகை பார் (DEMO, எதுவும் அனுப்பப்படாது).",
  "Frying oil per day against the RUCO threshold, TPC, and fill-weight giveaway and short fills.":
    "நாள்தோறும் பொரிக்கும் எண்ணெய் RUCO வரம்புடன், TPC, அதிக நிரப்பு மற்றும் குறை நிரப்பு.",
  "Five cards and today’s three actions, biggest rupee impact first.":
    "ஐந்து அட்டைகள் மற்றும் இன்றைய மூன்று செயல்கள், அதிக ரூபாய் தாக்கம் முதலில்.",
  "Each batch's cost against standard, as a waterfall. Tap ⓘ on any number.":
    "ஒவ்வொரு தொகுப்பின் செலவும் தரநிலையுடன் ஒப்பிட்டு, படிக்கட்டு வரைபடமாக. எந்த எண்ணிலும் ⓘ-ஐத் தட்டவும்.",
  "Registers, stock, production, ageing, GST, month-end close and the evidence pack.":
    "பதிவேடுகள், இருப்பு, உற்பத்தி, நிலுவை வயது, GST, மாத இறுதி முடிப்பு மற்றும் ஆதாரத் தொகுப்பு.",
  "Thresholds, prices and GST rates. A change applies from a date; the past never changes.":
    "வரம்புகள், விலைகள் மற்றும் GST விகிதங்கள். மாற்றம் ஒரு தேதியிலிருந்து பொருந்தும்; கடந்தது ஒருபோதும் மாறாது.",
  // ---------- home ----------
  "Order-to-audit system for a small snack factory":
    "சிறிய சிற்றுண்டித் தொழிற்சாலைக்கான ஆர்டர் முதல் தணிக்கை வரையிலான அமைப்பு",
  "Every gram traced. Every rupee explained.":
    "ஒவ்வொரு கிராமும் கண்டறியப்படும். ஒவ்வொரு ரூபாயும் விளக்கப்படும்.",
  "Most billing apps record what was sold. AaharOS explains what was":
    "பெரும்பாலான பில்லிங் செயலிகள் விற்றதை மட்டும் பதிவு செய்கின்றன. AaharOS விளக்குவது: என்ன",
  made: "செய்யப்பட்டது",
  ", what it": ", அதற்கு என்ன",
  cost: "செலவானது",
  ", where the profit": ", லாபம் எங்கே",
  leaked: "கசிந்தது",
  ", and what to do": ", அடுத்து என்ன",
  next: "செய்ய வேண்டும்",
  "Start the guided tour →": "வழிகாட்டும் சுற்றுலாவைத் தொடங்கு →",
  "How it works in one picture": "ஒரே படத்தில் எப்படி வேலை செய்கிறது",
  "Sales loop": "விற்பனைச் சுழற்சி",
  "Salesman order": "விற்பனையாளர் ஆர்டர்",
  "Admin approves": "நிர்வாகி ஒப்புதல்",
  "GST invoice": "GST விலைப்பட்டியல்",
  Dispatch: "அனுப்புதல்",
  Payment: "பணம் செலுத்துதல்",
  "Both loops meet at": "இரண்டு சுழற்சிகளும் சந்திக்கும் இடம்:",
  "finished-goods stock": "முடிந்த பொருட்களின் இருப்பு",
  "Production loop": "உற்பத்திச் சுழற்சி",
  Purchase: "கொள்முதல்",
  "Issue per recipe": "செய்முறைப்படி வழங்கல்",
  "Production batch": "உற்பத்தித் தொகுப்பு",
  "Good packets": "நல்ல பாக்கெட்டுகள்",
  "Cost & variance": "செலவு மற்றும் வேறுபாடு",
  "Everything above flows into the month's reports for the auditor. Each entry is made once, where it happens.":
    "மேலே உள்ள அனைத்தும் தணிக்கையாளருக்கான மாத அறிக்கைகளில் சேரும். ஒவ்வொரு பதிவும் நடக்கும் இடத்திலேயே ஒரே முறை செய்யப்படுகிறது.",
  "Two ways to start": "தொடங்க இரண்டு வழிகள்",
  "Follow the guided tour": "வழிகாட்டும் சுற்றுலாவைப் பின்பற்று",
  "One working day of the factory, step by step: who does it, where to click, what to type, and the number you should see. A voice reads each step aloud, in English or Tamil. Open it any time with the":
    "தொழிற்சாலையின் ஒரு வேலை நாள், படிப்படியாக: யார் செய்வது, எங்கே கிளிக் செய்வது, என்ன தட்டச்சு செய்வது, என்ன எண் தெரிய வேண்டும். ஒவ்வொரு படியையும் ஒரு குரல் ஆங்கிலத்திலோ தமிழிலோ வாசிக்கும். எப்போது வேண்டுமானாலும் திறக்க:",
  "button at the bottom right.": "பொத்தான், கீழே வலதுபுறம்.",
  "Start the tour →": "சுற்றுலாவைத் தொடங்கு →",
  "After the tour": "சுற்றுலாவுக்குப் பிறகு",
  "Work in your own factory": "உங்கள் சொந்தத் தொழிற்சாலையில் வேலை செய்யுங்கள்",
  "Create your own factory: a private copy that starts with the same opening stock, recipe and prices, with you as its Owner. Or look around the shared DEMO factory with a one-tap login for each role.":
    "உங்கள் சொந்தத் தொழிற்சாலையை உருவாக்குங்கள்: அதே தொடக்க இருப்பு, செய்முறை மற்றும் விலைகளுடன் தொடங்கும் தனிப்பட்ட நகல், நீங்களே அதன் உரிமையாளர். அல்லது ஒவ்வொரு பங்குக்கும் ஒரே தட்டல் உள்நுழைவுடன் பகிரப்பட்ட DEMO தொழிற்சாலையைச் சுற்றிப் பாருங்கள்.",
  "Create your own factory": "உங்கள் சொந்தத் தொழிற்சாலையை உருவாக்கு",
  "create your own factory": "உங்கள் சொந்தத் தொழிற்சாலையை உருவாக்கு",
  "Use a DEMO login": "DEMO உள்நுழைவைப் பயன்படுத்து",
  "Who uses it": "யார் பயன்படுத்துகிறார்கள்",
  "Factory admin": "தொழிற்சாலை நிர்வாகி",
  "Production supervisor": "உற்பத்தி மேற்பார்வையாளர்",
  Phone: "தொலைபேசி",
  Desktop: "கணினி",
  Tablet: "டேப்லெட்",
  Any: "எதுவும்",
  "Desktop, read-only": "கணினி, படிக்க மட்டும்",
  "Place an order for a shop in under 30 seconds, even offline.":
    "ஒரு கடைக்கான ஆர்டரை 30 விநாடிகளுக்குள் பதிவு செய்யுங்கள், இணையம் இல்லாவிட்டாலும்.",
  "Approve orders without overselling, raise GST invoices, dispatch, collect.":
    "அதிகமாக விற்காமல் ஆர்டர்களை ஒப்புக்கொள், GST விலைப்பட்டியல் இடு, அனுப்பு, வசூல் செய்.",
  "Record a batch like the paper batch sheet: planned vs actual.":
    "காகிதத் தொகுப்புத் தாள் போலவே தொகுப்பைப் பதிவு செய்: திட்டமிட்டது மற்றும் உண்மையானது.",
  "See today's 3 actions and where profit leaks, in rupees.":
    "இன்றைய 3 செயல்களையும் லாபம் எங்கே கசிகிறது என்பதையும் ரூபாயில் பாருங்கள்.",
  "Download the month's reports and trace any number to its source.":
    "மாத அறிக்கைகளைப் பதிவிறக்கி, எந்த எண்ணையும் அதன் மூலத்துக்குக் கண்டறியுங்கள்.",
  "Open the salesman screen →": "விற்பனையாளர் திரையைத் திற →",
  "Open the factory admin screen →": "தொழிற்சாலை நிர்வாகி திரையைத் திற →",
  "Open the production supervisor screen →": "உற்பத்தி மேற்பார்வையாளர் திரையைத் திற →",
  "Open the owner screen →": "உரிமையாளர் திரையைத் திற →",
  "Open the auditor screen →": "தணிக்கையாளர் திரையைத் திற →",
  // ---------- guided tour chrome ----------
  "← Back": "← பின்",
  "Finish the tour": "சுற்றுலாவை முடி",
  "Take me there": "அங்கே அழைத்துச் செல்",
  "You have finished the guided tour": "வழிகாட்டும் சுற்றுலாவை முடித்துவிட்டீர்கள்",
  "Sign in to my account": "என் கணக்கில் உள்நுழை",
  "Restart the tour": "சுற்றுலாவை மீண்டும் தொடங்கு",
  "Continue the tour →": "சுற்றுலாவைத் தொடர் →",
  "Take the guided tour first": "முதலில் வழிகாட்டும் சுற்றுலாவை முடியுங்கள்",
  Step: "படி",
  of: "இல்",
  Who: "யார்",
  Where: "எங்கே",
  What: "என்ன",
  "What to do": "என்ன செய்ய வேண்டும்",
  "What you should see": "நீங்கள் பார்க்க வேண்டியது",
  "Why it matters": "இது ஏன் முக்கியம்",
  "Tour progress": "சுற்றுலா முன்னேற்றம்",
  "Tour steps": "சுற்றுலாப் படிகள்",
  "Next:": "அடுத்து:",
  "No login needed": "உள்நுழைவு தேவையில்லை",
  Visitor: "பார்வையாளர்",
  "Salesman A": "விற்பனையாளர் A",
  "Salesman B, then Factory admin": "விற்பனையாளர் B, பிறகு தொழிற்சாலை நிர்வாகி",
  "Auditor (read-only)": "தணிக்கையாளர் (படிக்க மட்டும்)",
  "Salesman app → New order": "விற்பனையாளர் செயலி → புதிய ஆர்டர்",
  "Purchases → New receipt": "கொள்முதல் → புதிய ரசீது",
  "Production → Batch card": "உற்பத்தி → தொகுப்பு அட்டை",
  "Batch → Run costs": "தொகுப்பு → தொகுப்புச் செலவுகள்",
  "Admin → Order inbox": "நிர்வாகம் → ஆர்டர் பெட்டி",
  "Admin → Collections": "நிர்வாகம் → வசூல்",
  "Owner → Morning brief": "உரிமையாளர் → காலைச் சுருக்கம்",
  "Owner → Settings": "உரிமையாளர் → அமைப்புகள்",
  "Auditor → Reports": "தணிக்கையாளர் → அறிக்கைகள்",
  "Production → Batch planner": "உற்பத்தி → தொகுப்புத் திட்டமிடல்",
  "Production → Trace and recall": "உற்பத்தி → கண்டறிதல் மற்றும் திரும்பப் பெறுதல்",
  "Production → Oil and fill weights": "உற்பத்தி → எண்ணெய் மற்றும் நிரப்பு எடை",
  "Admin → Invoices and dispatch": "நிர்வாகம் → விலைப்பட்டியல் மற்றும் அனுப்புதல்",
  "Admin → Trips and cost-to-serve": "நிர்வாகம் → பயணங்கள் மற்றும் சேவைச் செலவு",
  "Production → Run costs": "உற்பத்தி → தொகுப்புச் செலவுகள்",
  "Salesman → Today": "விற்பனையாளர் → இன்று",
  "Salesman → My orders": "விற்பனையாளர் → என் ஆர்டர்கள்",
  "Salesman → Summary": "விற்பனையாளர் → சுருக்கம்",
  "Salesman → Freshness": "விற்பனையாளர் → புத்துணர்ச்சி",
  "steps seen. When you finish, the tour offers to continue with your own account.":
    "படிகள் பார்க்கப்பட்டன. முடித்ததும், உங்கள் சொந்தக் கணக்கில் தொடர சுற்றுலா வாய்ப்பளிக்கும்.",
  "short steps · about 8 minutes": "சிறு படிகள் · சுமார் 8 நிமிடங்கள்",
  // tour "what you should see" labels
  "Opening flour": "தொடக்க மாவு",
  "Opening cooking oil": "தொடக்க சமையல் எண்ணெய்",
  "Opening finished packets": "தொடக்க முடிந்த பாக்கெட்டுகள்",
  "Variance tolerance": "வேறுபாட்டு அனுமதி",
  "GST rate": "GST விகிதம்",
  "Flour average cost (weighted average)": "மாவின் சராசரி விலை (எடையிட்ட சராசரி)",
  "Flour left": "மீதமுள்ள மாவு",
  "Oil left": "மீதமுள்ள எண்ணெய்",
  "Spice mix left": "மீதமுள்ள மசாலா கலவை",
  "Finished packets in stock": "இருப்பில் உள்ள முடிந்த பாக்கெட்டுகள்",
  "Pouches left": "மீதமுள்ள பைகள்",
  "Cartons left": "மீதமுள்ள அட்டைப்பெட்டிகள்",
  "Yield variance": "விளைச்சல் வேறுபாடு",
  "Oil variance": "எண்ணெய் வேறுபாடு",
  "Pouches vs good packets": "பைகள் மற்றும் நல்ல பாக்கெட்டுகள்",
  "Packets ordered": "ஆர்டர் செய்த பாக்கெட்டுகள்",
  "Order value ex-tax": "வரிக்கு முந்தைய ஆர்டர் மதிப்பு",
  "Status after Save": "சேமித்த பின் நிலை",
  "Received by factory": "தொழிற்சாலை பெற்றது",
  "Taxable value": "வரிக்குரிய மதிப்பு",
  "Invoice total": "விலைப்பட்டியல் மொத்தம்",
  "Finished packets left": "மீதமுள்ள முடிந்த பாக்கெட்டுகள்",
  "Sent from the opening lot": "தொடக்க லாட்டிலிருந்து அனுப்பியது",
  "Sent from batch B-001": "தொகுப்பு B-001-இலிருந்து அனுப்பியது",
  Requested: "கேட்டது",
  Available: "கிடைப்பது",
  Shortage: "பற்றாக்குறை",
  "Tax if invoiced (other state)": "விலைப்பட்டியல் இட்டால் வரி (வேறு மாநிலம்)",
  "IGST if sent in full": "முழுவதும் அனுப்பினால் IGST",
  "e-Way Bill required?": "e-Way Bill தேவையா?",
  "Shortage caused by this batch's lost packets":
    "இந்தத் தொகுப்பின் இழந்த பாக்கெட்டுகளால் ஏற்பட்ட பற்றாக்குறை",
  "Retailer A still owes": "சில்லறை வியாபாரி A இன்னும் தர வேண்டியது",
  "Total batch cost": "தொகுப்பின் மொத்தச் செலவு",
  "Cost per good packet": "ஒரு நல்ல பாக்கெட்டின் செலவு",
  "Same batch with FIFO": "அதே தொகுப்பு FIFO முறையில்",
  "Same batch with last price": "அதே தொகுப்பு கடைசி விலையில்",
  "Cost above standard": "தரநிலைக்கு மேலான செலவு",
  "Full batches the stock allows after the run":
    "தொகுப்புக்குப் பின் இருப்பு அனுமதிக்கும் முழுத் தொகுப்புகள்",
  "Runs out first": "முதலில் தீர்வது",
  "Batches the pouches allow": "பைகள் அனுமதிக்கும் தொகுப்புகள்",
  "runs out first": "முதலில் தீர்வது",
  "Approving a plan": "திட்டத்துக்கு ஒப்புதல் அளித்தல்",
  "creates a draft, never a posting": "வரைவை மட்டும் உருவாக்கும், பதிவை அல்ல",
  "A recall simulation": "திரும்பப் பெறுதல் ஒத்திகை",
  "lists customers and invoices, sends nothing":
    "வாடிக்கையாளர்களையும் விலைப்பட்டியல்களையும் பட்டியலிடும், எதையும் அனுப்பாது",
  "GST summary: CGST": "GST சுருக்கம்: CGST",
  "GST summary: SGST": "GST சுருக்கம்: SGST",
  "Every report row": "ஒவ்வொரு அறிக்கை வரியும்",
  "links to its source document": "அதன் மூல ஆவணத்துடன் இணைக்கப்பட்டுள்ளது",
  Results: "முடிவுகள்",
  "26 of 26 correct": "26-இல் 26 சரி",
  yes: "ஆம்",
  no: "இல்லை",
  No: "இல்லை",
  Yes: "ஆம்",
  false: "இல்லை",
  true: "ஆம்",
  "not required": "தேவையில்லை",
  // ---------- instructions page ----------
  Instructions: "வழிமுறைகள்",
  "Instructions (step by step)": "வழிமுறைகள் (படிப்படியாக)",
  Listen: "கேள்",
  "Step-by-step: the guided tour, your own factory, and where the voice guide is. Listen in English or Tamil.":
    "படிப்படியாக: வழிகாட்டும் சுற்றுலா, உங்கள் சொந்தத் தொழிற்சாலை, குரல் வழிகாட்டி எங்கே உள்ளது. ஆங்கிலத்திலோ தமிழிலோ கேளுங்கள்.",
  "AaharOS runs a small snack factory from order to audit: salesmen take orders on the phone, the admin approves, invoices and dispatches, production records every batch and its cost, the owner sees where profit leaks, and the auditor downloads the month. Every number can be traced to the record it came from.":
    "AaharOS ஒரு சிறிய சிற்றுண்டித் தொழிற்சாலையை ஆர்டர் முதல் தணிக்கை வரை இயக்குகிறது: விற்பனையாளர்கள் தொலைபேசியில் ஆர்டர் எடுக்கிறார்கள், நிர்வாகி ஒப்புதல் அளித்து, விலைப்பட்டியல் இட்டு, அனுப்புகிறார், உற்பத்திப் பிரிவு ஒவ்வொரு தொகுப்பையும் அதன் செலவையும் பதிவு செய்கிறது, உரிமையாளர் லாபம் எங்கே கசிகிறது என்று பார்க்கிறார், தணிக்கையாளர் மாதக் கணக்கைப் பதிவிறக்குகிறார். ஒவ்வொரு எண்ணையும் அது வந்த பதிவு வரை கண்டறியலாம்.",
  "Everyone follows the same two routines: first the guided tour (on the shared DEMO factory), then your own factory. Both are below, step by step.":
    "அனைவரும் ஒரே இரண்டு வழிமுறைகளைப் பின்பற்றுகிறார்கள்: முதலில் வழிகாட்டும் சுற்றுலா (பகிரப்பட்ட DEMO தொழிற்சாலையில்), பிறகு உங்கள் சொந்தத் தொழிற்சாலை. இரண்டும் கீழே படிப்படியாக உள்ளன.",
  "Why it is needed": "இது ஏன் தேவை",
  "Keep these steps beside the screen": "இந்தப் படிகளைத் திரைக்கு அருகில் வைத்திரு",
  "Open the full instructions →": "முழு வழிமுறைகளைத் திற →",
  "Open my Morning brief →": "என் காலைச் சுருக்கத்தைத் திற →",
  "Where is the voice guide?": "குரல் வழிகாட்டி எங்கே உள்ளது?",
  "Open the tour with the voice guide →": "குரல் வழிகாட்டியுடன் சுற்றுலாவைத் திற →",
  "Voice guide: every tour step and both instruction lists can be heard in English or Tamil (press தமிழ் at the top).":
    "குரல் வழிகாட்டி: ஒவ்வொரு சுற்றுலாப் படியையும் இரண்டு வழிமுறைப் பட்டியல்களையும் ஆங்கிலத்திலோ தமிழிலோ கேட்கலாம் (மேலே தமிழ் அழுத்துங்கள்).",
  "Open the Guided tour (menu → Guide → Guided tour, or Start the guided tour on the home page).":
    "வழிகாட்டும் சுற்றுலாவைத் திறங்கள் (பட்டியல் → வழிகாட்டி → வழிகாட்டும் சுற்றுலா, அல்லது முகப்புப் பக்கத்தில் வழிகாட்டும் சுற்றுலாவைத் தொடங்கு).",
  "Above every step card is the voice bar: press 🔊 Listen to this step to hear it, Pause or Stop at any time.":
    "ஒவ்வொரு படி அட்டைக்கும் மேலே குரல் பட்டை உள்ளது: கேட்க 🔊 இந்தப் படியைக் கேள் அழுத்துங்கள், எப்போது வேண்டுமானாலும் இடைநிறுத்து அல்லது நிறுத்து.",
  "Tick Read each step aloud and every step is read as you move with Next.":
    "ஒவ்வொரு படியையும் உரக்க வாசி என்பதைத் தேர்ந்தெடுத்தால், அடுத்து அழுத்தும்போது ஒவ்வொரு படியும் வாசிக்கப்படும்.",
  "Press தமிழ் in the top bar: the text and the voice change to Tamil at once. Press English to go back.":
    "மேல் பட்டியில் தமிழ் அழுத்துங்கள்: உரையும் குரலும் உடனே தமிழுக்கு மாறும். திரும்ப English அழுத்துங்கள்.",
  "On this Instructions page, 🔊 Listen reads each routine aloud as well.":
    "இந்த வழிமுறைகள் பக்கத்திலும், 🔊 கேள் ஒவ்வொரு வழிமுறையையும் உரக்க வாசிக்கும்.",
  "Stock is never guessed: every gram moves through a double-entry stock ledger and can never go below zero.":
    "இருப்பு ஒருபோதும் ஊகிக்கப்படுவதில்லை: ஒவ்வொரு கிராமும் இரட்டைப் பதிவு இருப்புப் பேரேட்டின் வழியே நகர்கிறது, பூஜ்யத்துக்குக் கீழே போகவே முடியாது.",
  "Cost is explained: each batch's cost per good packet comes from real material, labour and gas, and the gap against standard is shown step by step.":
    "செலவு விளக்கப்படுகிறது: ஒவ்வொரு தொகுப்பின் நல்ல பாக்கெட் செலவும் உண்மையான பொருள், கூலி மற்றும் எரிவாயுவிலிருந்து வருகிறது, தரநிலையுடனான இடைவெளி படிப்படியாகக் காட்டப்படுகிறது.",
  "Tax is consistent: invoice tax lines, the GST summary and the GSTR-1 file are the same numbers.":
    "வரி ஒரே மாதிரியாக இருக்கிறது: விலைப்பட்டியல் வரி வரிகள், GST சுருக்கம், GSTR-1 கோப்பு மூன்றும் ஒரே எண்கள்.",
  "Every number can be checked: tap ⓘ beside any figure to see its formula and source record.":
    "ஒவ்வொரு எண்ணையும் சரிபார்க்கலாம்: அதன் சூத்திரத்தையும் மூலப் பதிவையும் பார்க்க எந்த எண்ணுக்கும் அருகில் ⓘ தட்டுங்கள்.",
  "People are not slowed down: orders work offline on a phone, approval is one tap, month end is a download.":
    "மக்களின் வேலை தாமதமாவதில்லை: ஆர்டர்கள் இணையம் இல்லாமலும் தொலைபேசியில் வேலை செய்யும், ஒப்புதல் ஒரே தட்டல், மாத இறுதி ஒரு பதிவிறக்கம்.",
  // ---------- voice guide ----------
  "Sound on": "ஒலி இயக்கத்தில்",
  "Sound off": "ஒலி அணைப்பில்",
  "Sound on (turn off)": "ஒலி இயக்கத்தில் (அணைக்க)",
  "Sound off (turn on)": "ஒலி அணைப்பில் (இயக்க)",
  "I have done this step": "இந்தப் படியை முடித்துவிட்டேன்",
  "Do the step on the screen, tick the box, then press Next.":
    "திரையில் இந்தப் படியைச் செய்து, பெட்டியைத் தேர்ந்தெடுத்து, பிறகு அடுத்து அழுத்துங்கள்.",
  // tour finish panel and voice note
  "Almost there.": "கிட்டத்தட்ட முடிந்தது.",
  "Open every step once to finish the tour. Not seen yet:":
    "சுற்றுலாவை முடிக்க ஒவ்வொரு படியையும் ஒருமுறை திறக்கவும். இன்னும் பார்க்காதவை:",
  "Continue with your own account? Your own factory starts with the same data as the tour, and you can take the tour again at any time from the top bar.":
    "உங்கள் சொந்தக் கணக்கில் தொடர்கிறீர்களா? உங்கள் சொந்தத் தொழிற்சாலை சுற்றுலாவின் அதே தரவுடன் தொடங்கும், மேலே உள்ள பட்டியிலிருந்து எப்போது வேண்டுமானாலும் சுற்றுலாவை மீண்டும் எடுக்கலாம்.",
  "This device has no Tamil voice installed, so the reading may sound wrong. Microsoft Edge has one built in; on Windows you can also add Tamil speech in Settings → Time & language → Speech.":
    "இந்தச் சாதனத்தில் தமிழ்க் குரல் நிறுவப்படவில்லை, அதனால் வாசிப்பு சரியாக ஒலிக்காமல் போகலாம். Microsoft Edge-இல் தமிழ்க் குரல் உள்ளது; Windows-இல் அமைப்புகள் → நேரம் மற்றும் மொழி → பேச்சு என்பதில் தமிழ்ப் பேச்சையும் சேர்க்கலாம்.",
  "Voice guide": "குரல் வழிகாட்டி",
  "Listen to this step": "இந்தப் படியைக் கேள்",
  Pause: "இடைநிறுத்து",
  Resume: "தொடர்",
  Stop: "நிறுத்து",
  "Read each step aloud": "ஒவ்வொரு படியையும் உரக்க வாசி",
  "Speaking…": "பேசுகிறது…",
  "Voice is not available in this browser.": "இந்த உலாவியில் குரல் வசதி இல்லை.",
  // ---------- how-to panel ----------
  "Close the steps": "படிகளை மூடு",
  "Guided tour, step by step": "வழிகாட்டும் சுற்றுலா, படிப்படியாக",
  "Your own factory, step by step": "உங்கள் சொந்தத் தொழிற்சாலை, படிப்படியாக",
  "Keep this panel open and work on the screen beside it.":
    "இந்தப் பலகத்தைத் திறந்து வைத்து, அருகில் உள்ள திரையில் வேலை செய்யுங்கள்.",
  "Open the app and press Start the guided tour (or Restart tour in the top bar, at any time).":
    "செயலியைத் திறந்து வழிகாட்டும் சுற்றுலாவைத் தொடங்கு என்பதை அழுத்துங்கள் (அல்லது எப்போது வேண்டுமானாலும் மேல் பட்டியில் சுற்றுலாவை மீண்டும் தொடங்கு).",
  "Read the step card: who does it, where (Take me there opens the screen), what to do and what you should see.":
    "படி அட்டையைப் படியுங்கள்: யார் செய்வது, எங்கே (அங்கே அழைத்துச் செல் திரையைத் திறக்கும்), என்ன செய்வது, என்ன பார்க்க வேண்டும்.",
  "To hear it, press Listen to this step, or tick Read each step aloud. Press தமிழ் for Tamil text and a Tamil voice.":
    "கேட்க, இந்தப் படியைக் கேள் அழுத்துங்கள், அல்லது ஒவ்வொரு படியையும் உரக்க வாசி என்பதைத் தேர்ந்தெடுங்கள். தமிழ் உரைக்கும் தமிழ்க் குரலுக்கும் தமிழ் அழுத்துங்கள்.",
  "Sign in as the person the card names: on the sign-in page one tap on a DEMO login fills it in.":
    "அட்டை குறிப்பிடும் நபராக உள்நுழையுங்கள்: உள்நுழைவுப் பக்கத்தில் ஒரு DEMO உள்நுழைவை ஒருமுறை தட்டினால் அது நிரம்பும்.",
  "Do the step on the screen and compare your numbers with What you should see. Tap ⓘ on any number to see where it came from.":
    "திரையில் அந்தப் படியைச் செய்து, உங்கள் எண்களை நீங்கள் பார்க்க வேண்டியது என்பதுடன் ஒப்பிடுங்கள். எந்த எண் எங்கிருந்து வந்தது என்று பார்க்க அதில் ⓘ தட்டுங்கள்.",
  "Press the Guide button (bottom right) to come back to the same step, then press Next.":
    "அதே படிக்குத் திரும்ப வழிகாட்டி பொத்தானை (கீழே வலதுபுறம்) அழுத்துங்கள், பிறகு அடுத்து அழுத்துங்கள்.",
  "Repeat for all 12 steps. On the last step press Finish the tour.":
    "12 படிகளுக்கும் இதையே செய்யுங்கள். கடைசிப் படியில் சுற்றுலாவை முடி அழுத்துங்கள்.",
  "Choose Create your own factory, or Sign in to my account.":
    "உங்கள் சொந்தத் தொழிற்சாலையை உருவாக்கு, அல்லது என் கணக்கில் உள்நுழை என்பதைத் தேர்ந்தெடுங்கள்.",
  "Finish the guided tour on this device: creating a factory opens only after the tour.":
    "இந்தச் சாதனத்தில் வழிகாட்டும் சுற்றுலாவை முடியுங்கள்: சுற்றுலாவுக்குப் பிறகுதான் தொழிற்சாலையை உருவாக்க முடியும்.",
  "Press Create your own factory (on the finish panel, the home page or the sign-in page).":
    "உங்கள் சொந்தத் தொழிற்சாலையை உருவாக்கு என்பதை அழுத்துங்கள் (முடிவுப் பலகம், முகப்புப் பக்கம் அல்லது உள்நுழைவுப் பக்கத்தில்).",
  "Enter a factory name, your name, your email and a password of at least 10 characters, then press Create my factory.":
    "தொழிற்சாலையின் பெயர், உங்கள் பெயர், மின்னஞ்சல், குறைந்தது 10 எழுத்துகள் கொண்ட கடவுச்சொல் ஆகியவற்றை உள்ளிட்டு, என் தொழிற்சாலையை உருவாக்கு அழுத்துங்கள்.",
  "You are signed in as the Owner of a private factory with the same opening stock, recipe, customers and prices as the tour.":
    "சுற்றுலாவின் அதே தொடக்க இருப்பு, செய்முறை, வாடிக்கையாளர்கள் மற்றும் விலைகளுடன் கூடிய தனிப்பட்ட தொழிற்சாலையின் உரிமையாளராக நீங்கள் உள்நுழைந்துள்ளீர்கள்.",
  "Work through a day in the menu: Purchases → Batch card → Today (orders) → Order inbox → Invoices and dispatch → Collections → Run costs → Morning brief → Reports.":
    "பட்டியலில் ஒரு நாளை முடியுங்கள்: கொள்முதல் → தொகுப்பு அட்டை → இன்று (ஆர்டர்கள்) → ஆர்டர் பெட்டி → விலைப்பட்டியல் மற்றும் அனுப்புதல் → வசூல் → தொகுப்புச் செலவுகள் → காலைச் சுருக்கம் → அறிக்கைகள்.",
  "Change thresholds, prices or GST rates in Owner → Settings; a change applies from the date you pick.":
    "வரம்புகள், விலைகள் அல்லது GST விகிதங்களை உரிமையாளர் → அமைப்புகளில் மாற்றுங்கள்; நீங்கள் தேர்ந்தெடுக்கும் தேதியிலிருந்து மாற்றம் பொருந்தும்.",
  "Sign out from the top bar. Next time, sign in with the same email and password to continue where you left off.":
    "மேல் பட்டியிலிருந்து வெளியேறுங்கள். அடுத்த முறை, விட்ட இடத்திலிருந்து தொடர அதே மின்னஞ்சல் மற்றும் கடவுச்சொல்லுடன் உள்நுழையுங்கள்.",
  "Press Restart tour at any time to go over a step again.":
    "ஒரு படியை மீண்டும் பார்க்க எப்போது வேண்டுமானாலும் சுற்றுலாவை மீண்டும் தொடங்கு அழுத்துங்கள்.",
  "Create my factory": "என் தொழிற்சாலையை உருவாக்கு",
  "Setting up your factory…": "உங்கள் தொழிற்சாலை அமைக்கப்படுகிறது…",
  // ---------- sign in / sign up ----------
  Email: "மின்னஞ்சல்",
  Password: "கடவுச்சொல்",
  "Signing in…": "உள்நுழைகிறது…",
  "Signed in": "உள்நுழைந்துவிட்டீர்கள்",
  "Go to my home screen": "என் முகப்புத் திரைக்குச் செல்",
  "Factory name": "தொழிற்சாலையின் பெயர்",
  "Your name": "உங்கள் பெயர்",
  "Password (at least 10 characters)": "கடவுச்சொல் (குறைந்தது 10 எழுத்துகள்)",
  "Creating your factory…": "உங்கள் தொழிற்சாலை உருவாகிறது…",
  "Takes orders on the phone": "தொலைபேசியில் ஆர்டர் எடுக்கிறார்",
  "Approves, invoices, dispatches": "ஒப்புதல், விலைப்பட்டியல், அனுப்புதல்",
  "Purchases and batches": "கொள்முதல் மற்றும் தொகுப்புகள்",
  "Sees where profit leaks": "லாபம் எங்கே கசிகிறது என்று பார்க்கிறார்",
  "Reads everything, changes nothing": "அனைத்தையும் படிக்கிறார், எதையும் மாற்றுவதில்லை",
  "Organization code (only if your login belongs to several)":
    "நிறுவனக் குறியீடு (உங்கள் உள்நுழைவு பலவற்றுக்குச் சொந்தமானால் மட்டும்)",
  "Everyone shares this DEMO factory. After the":
    "அனைவரும் இந்த DEMO தொழிற்சாலையைப் பகிர்கிறார்கள். பின்வருவதற்குப் பிறகு:",
  "guided tour": "வழிகாட்டும் சுற்றுலா",
  ", sign in with your own account or": ", உங்கள் சொந்தக் கணக்கில் உள்நுழையுங்கள் அல்லது",
  "Wrong email or password.": "மின்னஞ்சல் அல்லது கடவுச்சொல் தவறு.",
  "Confirm your email address first.": "முதலில் உங்கள் மின்னஞ்சல் முகவரியை உறுதிப்படுத்துங்கள்.",
  ", follow the guided tour once with the shared DEMO logins, so the workflow makes sense: order → approval → GST invoice → dispatch → payment, and purchase → batch → cost → where profit leaks.":
    ", பகிரப்பட்ட DEMO உள்நுழைவுகளுடன் ஒருமுறை வழிகாட்டும் சுற்றுலாவைப் பின்பற்றுங்கள், அப்போது வேலைமுறை புரியும்: ஆர்டர் → ஒப்புதல் → GST விலைப்பட்டியல் → அனுப்புதல் → பணம், மற்றும் கொள்முதல் → தொகுப்பு → செலவு → லாபம் எங்கே கசிகிறது.",
  "Before you": "இதற்கு முன்",
  // ---------- people, roles, fragments ----------
  OWNER: "உரிமையாளர்",
  ADMIN: "நிர்வாகி",
  SALESMAN: "விற்பனையாளர்",
  PRODUCTION: "உற்பத்தி",
  AUDITOR: "தணிக்கையாளர்",
  "Owner (DEMO)": "உரிமையாளர் (DEMO)",
  "Factory Admin (DEMO)": "தொழிற்சாலை நிர்வாகி (DEMO)",
  "Production Supervisor (DEMO)": "உற்பத்தி மேற்பார்வையாளர் (DEMO)",
  "Auditor (DEMO)": "தணிக்கையாளர் (DEMO)",
  "Salesman A (DEMO)": "விற்பனையாளர் A (DEMO)",
  "Salesman B (DEMO)": "விற்பனையாளர் B (DEMO)",
  "packets ·": "பாக்கெட்டுகள் ·",
  "good packets ·": "நல்ல பாக்கெட்டுகள் ·",
  "· batch": "· தொகுப்பு",
  good: "நல்லவை",
  "good packets each": "நல்ல பாக்கெட்டுகள் ஒவ்வொன்றிலும்",
  ": make": ": தயாரிக்க",
  ", about": ", சுமார்",
  "): stock allows": "): இருப்பு அனுமதிப்பது",
  "Value ex-tax": "வரிக்கு முந்தைய மதிப்பு",
  "Opening stock": "தொடக்க இருப்பு",
  "In the books": "கணக்கில்",
  checked: "சரிபார்த்தது",
  "· generated": "· உருவாக்கியது",
  "· e-Way Bill": "· e-Way Bill",
  "estimated (straight line x road factor)": "மதிப்பீடு (நேர்கோடு × சாலைக் காரணி)",
  "MURUKKU-200G": "முறுக்கு 200 கி",
  "MURUKKU-500G": "முறுக்கு 500 கி",
  "none below 191 g": "191 g-க்குக் கீழ் எதுவும் இல்லை",
  "Short if below declared minus: 200 g → 9 g, 500 g → 15 g.":
    "அறிவித்த எடையிலிருந்து இதைக் கழித்ததற்குக் கீழே இருந்தால் குறைவு: 200 g → 9 g, 500 g → 15 g.",
  "Credit notes: - to - (0 cancelled)": "கடன் குறிப்புகள்: - முதல் - வரை (0 ரத்து)",
  // ---------- common words and buttons ----------
  Open: "திற",
  Close: "மூடு",
  Change: "மாற்று",
  Save: "சேமி",
  Cancel: "ரத்து செய்",
  Show: "காட்டு",
  Search: "தேடு",
  Done: "முடிந்தது",
  done: "முடிந்தது",
  All: "அனைத்தும்",
  Day: "நாள்",
  Month: "மாதம்",
  From: "முதல்",
  To: "வரை",
  Until: "வரை",
  open: "திறந்துள்ளது",
  Total: "மொத்தம்",
  Product: "பொருள்",
  Products: "பொருட்கள்",
  Item: "பொருள்",
  Unit: "அலகு",
  unit: "அலகு",
  Quantity: "அளவு",
  Rate: "விகிதம்",
  "Rate (%)": "விகிதம் (%)",
  Reason: "காரணம்",
  Reference: "குறிப்பு",
  Mode: "முறை",
  Method: "முறை",
  Note: "குறிப்பு",
  Source: "மூலம்",
  Status: "நிலை",
  Result: "முடிவு",
  Check: "சரிபார்",
  Expected: "எதிர்பார்ப்பு",
  Customer: "வாடிக்கையாளர்",
  Supplier: "சப்ளையர்",
  Retailer: "சில்லறை வியாபாரி",
  Distributor: "விநியோகஸ்தர்",
  "Tamil Nadu": "தமிழ்நாடு",
  Karnataka: "கர்நாடகா",
  History: "வரலாறு",
  Timeline: "காலவரிசை",
  Decide: "முடிவு செய்",
  Credit: "கடன்",
  Delivery: "விநியோகம்",
  Returns: "திருப்பி அனுப்பியவை",
  Invoice: "விலைப்பட்டியல்",
  Invoices: "விலைப்பட்டியல்கள்",
  Orders: "ஆர்டர்கள்",
  Documents: "ஆவணங்கள்",
  Table: "அட்டவணை",
  Packets: "பாக்கெட்டுகள்",
  packets: "பாக்கெட்டுகள்",
  packet: "பாக்கெட்",
  piece: "துண்டு",
  pieces: "துண்டுகள்",
  batches: "தொகுப்புகள்",
  days: "நாட்கள்",
  "days.": "நாட்கள்.",
  Batch: "தொகுப்பு",
  Batches: "தொகுப்புகள்",
  Material: "பொருள்",
  Materials: "பொருட்கள்",
  Packaging: "பொதியிடல்",
  Planned: "திட்டமிட்டது",
  Actual: "உண்மையானது",
  "Actual now": "இப்போதைய உண்மை",
  Paid: "செலுத்தியது",
  Owed: "தர வேண்டியது",
  owes: "தர வேண்டியது",
  Due: "செலுத்த வேண்டிய தேதி",
  Outstanding: "நிலுவை",
  "Overdue:": "காலம் கடந்தது:",
  Taxable: "வரிக்குரியது",
  taxable: "வரிக்குரியது",
  Tax: "வரி",
  "ex-tax": "வரிக்கு முன்",
  "before tax": "வரிக்கு முன்",
  "before tax.": "வரிக்கு முன்.",
  Short: "குறைவு",
  Fresh: "புதியது",
  Flagged: "குறிக்கப்பட்டது",
  Posted: "பதிவு செய்யப்பட்டது",
  Dispatched: "அனுப்பப்பட்டது",
  Received: "பெறப்பட்டது",
  "Received on": "பெற்ற தேதி",
  provisional: "தற்காலிகம்",
  "in progress": "நடைபெறுகிறது",
  draft: "வரைவு",
  Draft: "வரைவு",
  Cancelled: "ரத்து செய்யப்பட்டது",
  Pass: "தேர்ச்சி",
  Passing: "தேர்ச்சி",
  correct: "சரி",
  "not correct": "சரியில்லை",
  Integrity: "நேர்மை",
  Security: "பாதுகாப்பு",
  "Choose…": "தேர்ந்தெடு…",
  "Loading…": "ஏற்றுகிறது…",
  "Not run yet": "இன்னும் இயக்கவில்லை",
  DEMO: "DEMO",
  "with the factory": "தொழிற்சாலையுடன்",
  "With the factory": "தொழிற்சாலையுடன்",
  // ---------- salesman ----------
  "Today's customers": "இன்றைய வாடிக்கையாளர்கள்",
  "In route order. Tap": "வழி வரிசையில். தட்டவும்:",
  ", or": ", அல்லது",
  "to start from what they took last time.": "கடந்த முறை எடுத்ததிலிருந்து தொடங்க.",
  "Repeat last order": "கடைசி ஆர்டரை மீண்டும் செய்",
  "← Today": "← இன்று",
  "← My orders": "← என் ஆர்டர்கள்",
  "/ packet ex-tax": "/ பாக்கெட் வரிக்கு முன்",
  "Save order": "ஆர்டரைச் சேமி",
  "· estimated, ex-tax": "· மதிப்பீடு, வரிக்கு முன்",
  "Prices come from the factory's price list (":
    "விலைகள் தொழிற்சாலையின் விலைப்பட்டியலிலிருந்து வருகின்றன (",
  "). GST is added on the invoice. The factory confirms the total when it receives the order.":
    "). GST விலைப்பட்டியலில் சேர்க்கப்படும். ஆர்டரைப் பெற்றதும் தொழிற்சாலை மொத்தத்தை உறுதிப்படுத்தும்.",
  "Saved on phone": "தொலைபேசியில் சேமிக்கப்பட்டது",
  "Received by factory as": "தொழிற்சாலை பெற்றது, எண்:",
  "Approval by the factory admin": "தொழிற்சாலை நிர்வாகியின் ஒப்புதல்",
  "Order value ex-tax:": "வரிக்கு முந்தைய ஆர்டர் மதிப்பு:",
  "Price ex-tax": "வரிக்கு முந்தைய விலை",
  "Total ordered, ex-tax": "மொத்த ஆர்டர், வரிக்கு முன்",
  "these are order values before GST, not sales.":
    "இவை GST-க்கு முந்தைய ஆர்டர் மதிப்புகள், விற்பனை அல்ல.",
  "Packets that may still be on your customers’ shelves, oldest best-before first. Visit the flagged ones before the packets expire.":
    "உங்கள் வாடிக்கையாளர்களின் அலமாரிகளில் இன்னும் இருக்கக்கூடிய பாக்கெட்டுகள், பழைய காலாவதி முதலில். பாக்கெட்டுகள் காலாவதியாகும் முன் குறிக்கப்பட்டவர்களைச் சந்தியுங்கள்.",
  "may be on the shelf": "அலமாரியில் இருக்கலாம்",
  "nothing expires within 15 days": "15 நாட்களுக்குள் எதுவும் காலாவதியாகாது",
  "(not enough order history to say more)": "(மேலும் சொல்லப் போதுமான ஆர்டர் வரலாறு இல்லை)",
  "An estimate from each customer's order rhythm over the last 90 days, not a shelf count: the low and high come from their fastest and slowest gaps between orders.":
    "கடந்த 90 நாட்களில் ஒவ்வொரு வாடிக்கையாளரின் ஆர்டர் இடைவெளியிலிருந்து ஒரு மதிப்பீடு, அலமாரி எண்ணிக்கை அல்ல: குறைந்ததும் அதிகமும் அவர்களின் மிக வேகமான மற்றும் மிக மெதுவான ஆர்டர் இடைவெளிகளிலிருந்து வருகின்றன.",
  // ---------- admin: inbox, order card ----------
  "Orders from the salesmen. Open one to approve it, send part now, wait for the next batch, or reject it. Stock is held for an order the moment you approve it.":
    "விற்பனையாளர்களிடமிருந்து வந்த ஆர்டர்கள். ஒன்றைத் திறந்து ஒப்புக்கொள்ளுங்கள், இப்போது ஒரு பகுதியை அனுப்புங்கள், அடுத்த தொகுப்புக்குக் காத்திருங்கள், அல்லது நிராகரியுங்கள். ஒப்புதல் அளித்த உடனேயே அந்த ஆர்டருக்கு இருப்பு ஒதுக்கப்படும்.",
  "To decide": "முடிவு செய்ய",
  "Stale price": "பழைய விலை",
  "Could not load the inbox.": "ஆர்டர் பெட்டியை ஏற்ற முடியவில்லை.",
  "← Order inbox": "← ஆர்டர் பெட்டி",
  "Products and stock": "பொருட்கள் மற்றும் இருப்பு",
  Ordered: "ஆர்டர் செய்தது",
  "Available to promise": "வழங்கக்கூடியது",
  "If invoiced": "விலைப்பட்டியல் இட்டால்",
  "Place of supply": "விநியோக இடம்",
  ". A preview: the invoice works it out again on its own date.":
    ". இது முன்னோட்டம்: விலைப்பட்டியல் தன் தேதியில் மீண்டும் கணக்கிடும்.",
  "no e-Way Bill needed": "e-Way Bill தேவையில்லை",
  "(DEMO check, nothing is filed)": "(DEMO சரிபார்ப்பு, எதுவும் தாக்கல் செய்யப்படாது)",
  "(DEMO, not filed)": "(DEMO, தாக்கல் செய்யப்படாது)",
  "+ this order =": "+ இந்த ஆர்டர் =",
  "against a limit of": "வரம்பு:",
  "Within limit": "வரம்புக்குள்",
  "Outstanding = invoices minus payments and credit notes.":
    "நிலுவை = விலைப்பட்டியல்கள் கழித்தல் பணம் மற்றும் கடன் குறிப்புகள்.",
  "The packets are held for this customer at once.":
    "பாக்கெட்டுகள் உடனே இந்த வாடிக்கையாளருக்கு ஒதுக்கப்படும்.",
  "Approve all": "அனைத்தையும் ஒப்புக்கொள்",
  "Edit an order line": "ஆர்டர் வரியைத் திருத்து",
  "Change the packets or the price before you decide. The reason is kept in the order's history and the audit trail.":
    "முடிவு செய்வதற்கு முன் பாக்கெட்டுகளையோ விலையையோ மாற்றுங்கள். காரணம் ஆர்டர் வரலாற்றிலும் தணிக்கைப் பதிவிலும் சேமிக்கப்படும்.",
  "New packets": "புதிய பாக்கெட்டுகள்",
  "New price ex-tax (₹)": "புதிய விலை வரிக்கு முன் (₹)",
  "Save the change": "மாற்றத்தைச் சேமி",
  "Reason for the change": "மாற்றத்துக்கான காரணம்",
  "Send what is available now": "இப்போது கிடைப்பதை அனுப்பு",
  "Wait for the next batch": "அடுத்த தொகுப்புக்குக் காத்திரு",
  Reject: "நிராகரி",
  APPROVED: "ஒப்புதல் அளிக்கப்பட்டது",
  Approved: "ஒப்புதல் அளிக்கப்பட்டது",
  DISPATCHED: "அனுப்பப்பட்டது",
  INVOICED: "விலைப்பட்டியல் இடப்பட்டது",
  "· from": "· அனுப்பியவர்",
  "· saved on phone": "· தொலைபேசியில் சேமித்தது",
  "· received": "· பெற்றது",
  // ---------- invoices, dispatch ----------
  "Approved orders become GST invoices here (CGST + SGST inside Tamil Nadu, IGST outside). Open an invoice to print it and to send the goods, oldest batch first.":
    "ஒப்புதல் பெற்ற ஆர்டர்கள் இங்கே GST விலைப்பட்டியல்களாகின்றன (தமிழ்நாட்டுக்குள் CGST + SGST, வெளியே IGST). அச்சிடவும் பொருட்களை அனுப்பவும் ஒரு விலைப்பட்டியலைத் திறக்கவும், பழைய தொகுப்பு முதலில்.",
  "Ready to invoice": "விலைப்பட்டியல் இடத் தயார்",
  "Create invoice": "விலைப்பட்டியல் உருவாக்கு",
  "No approved orders are waiting.": "ஒப்புதல் பெற்ற ஆர்டர்கள் எதுவும் காத்திருக்கவில்லை.",
  "← Invoices": "← விலைப்பட்டியல்கள்",
  "· order": "· ஆர்டர்",
  "· place of supply": "· விநியோக இடம்",
  "· due": "· செலுத்த வேண்டிய தேதி",
  HSN: "HSN",
  "Paid / credited": "செலுத்தியது / வரவு வைத்தது",
  "Still owed": "இன்னும் தர வேண்டியது",
  "Open printable invoice (PDF)": "அச்சிடக்கூடிய விலைப்பட்டியலைத் திற (PDF)",
  "Share on WhatsApp": "WhatsApp-இல் பகிர்",
  "The share links carry a text summary only; attach the PDF yourself.":
    "பகிர்வு இணைப்புகள் உரைச் சுருக்கத்தை மட்டுமே கொண்டு செல்லும்; PDF-ஐ நீங்களே இணையுங்கள்.",
  "Packets leave oldest batch first (first expiry, first out). Check the stock movement before you post it.":
    "பாக்கெட்டுகள் பழைய தொகுப்பிலிருந்து முதலில் வெளியேறும் (முதலில் காலாவதி, முதலில் வெளியே). பதிவு செய்யும் முன் இருப்பு நகர்வைச் சரிபாருங்கள்.",
  "Stock movement": "இருப்பு நகர்வு",
  "Record dispatch": "அனுப்புதலைப் பதிவு செய்",
  "Not now": "இப்போது வேண்டாம்",
  "e-Way Bill not required": "e-Way Bill தேவையில்லை",
  "e-Way Bill required": "e-Way Bill தேவை",
  "Credit note (price correction, discount, short supply)":
    "கடன் குறிப்பு (விலைத் திருத்தம், தள்ளுபடி, குறைவான விநியோகம்)",
  "Post credit note": "கடன் குறிப்பைப் பதிவு செய்",
  "Cancel this invoice (only before dispatch)":
    "இந்த விலைப்பட்டியலை ரத்து செய் (அனுப்புவதற்கு முன் மட்டும்)",
  "Cancel invoice": "விலைப்பட்டியலை ரத்து செய்",
  // ---------- collections ----------
  "What each customer owes: invoice totals minus payments and credit notes. Total owed:":
    "ஒவ்வொரு வாடிக்கையாளரும் தர வேண்டியது: விலைப்பட்டியல் மொத்தம் கழித்தல் பணம் மற்றும் கடன் குறிப்புகள். மொத்த நிலுவை:",
  "Not yet due": "இன்னும் கெடு வரவில்லை",
  "Nothing owed": "நிலுவை இல்லை",
  "· terms": "· கால அவகாசம்",
  "Record a payment": "பணம் பெற்றதைப் பதிவு செய்",
  "Amount (₹)": "தொகை (₹)",
  "Record payment": "பணத்தைப் பதிவு செய்",
  "It is applied to the oldest unpaid invoice first; anything left is kept as an advance.":
    "இது முதலில் பழைய செலுத்தப்படாத விலைப்பட்டியலுக்குப் பொருந்தும்; மீதி முன்பணமாக வைக்கப்படும்.",
  "Unpaid more than 45 days (MSME clock):": "45 நாட்களுக்கு மேல் செலுத்தப்படாதது (MSME கணக்கு):",
  UPI: "UPI",
  CASH: "ரொக்கம்",
  BANK: "வங்கி",
  CHEQUE: "காசோலை",
  // ---------- trips ----------
  "Plan delivery trips from a day's dispatch notes, record what was actually driven, and see what serving each customer costs. Management figures only: nothing is posted.":
    "ஒரு நாளின் அனுப்புதல் குறிப்புகளிலிருந்து விநியோகப் பயணங்களைத் திட்டமிடுங்கள், உண்மையில் ஓட்டியதைப் பதிவு செய்யுங்கள், ஒவ்வொரு வாடிக்கையாளருக்கும் சேவை செய்ய ஆகும் செலவைப் பாருங்கள். மேலாண்மை எண்கள் மட்டும்: எதுவும் பதிவு செய்யப்படாது.",
  "Plan a day": "ஒரு நாளைத் திட்டமிடு",
  "Dispatch date": "அனுப்பிய தேதி",
  "Distances:": "தூரங்கள்:",
  "Trips (last 30 days)": "பயணங்கள் (கடந்த 30 நாட்கள்)",
  Trip: "பயணம்",
  Stops: "நிறுத்தங்கள்",
  "Cost-to-serve and the Deal Desk (last 30 days)":
    "சேவைச் செலவு மற்றும் விலை மேசை (கடந்த 30 நாட்கள்)",
  "Price floor": "குறைந்தபட்ச விலை",
  "Rupees per packet": "ஒரு பாக்கெட்டுக்கு ரூபாய்",
  "Per packet": "ஒரு பாக்கெட்டுக்கு",
  "is waiting for a trip.": "பயணத்துக்குக் காத்திருக்கிறது.",
  "No dispatch note of": "இந்தத் தேதியின் அனுப்புதல் குறிப்பு எதுவும் இல்லை:",
  "DEMO mini truck": "DEMO சிறிய லாரி",
  "DEMO two-wheeler": "DEMO இருசக்கர வாகனம்",
  "Delivery (each customer's share of trip costs, by packets) + credit (what they owe, at the factory's rate of money) + returns. The floor is the lowest ex-tax price per packet that still covers the product and the cost of serving them.":
    "விநியோகம் (பாக்கெட்டுகளின் அடிப்படையில் பயணச் செலவில் ஒவ்வொரு வாடிக்கையாளரின் பங்கு) + கடன் (அவர்கள் தர வேண்டியது, தொழிற்சாலையின் பண விகிதத்தில்) + திருப்பி அனுப்பியவை. குறைந்தபட்ச விலை என்பது பொருளையும் சேவைச் செலவையும் ஈடுகட்டும் ஒரு பாக்கெட்டின் மிகக் குறைந்த வரிக்கு முந்தைய விலை.",
  "Distances are straight-line x the road factor (DEMO setting), not a road map. Costs are management figures and are not posted. CO2 is an estimate.":
    "தூரங்கள் நேர்கோடு × சாலைக் காரணி (DEMO அமைப்பு), சாலை வரைபடம் அல்ல. செலவுகள் மேலாண்மை எண்கள், பதிவு செய்யப்படுவதில்லை. CO2 ஒரு மதிப்பீடு.",
  "km ·": "கி.மீ. ·",
  km: "கி.மீ.",
  // ---------- purchases ----------
  "New purchase receipt": "புதிய கொள்முதல் ரசீது",
  "What arrived from the supplier. It is added to stock at quantity × rate, and the average cost updates by itself. Record the supplier's lot number so a recall can find it.":
    "சப்ளையரிடமிருந்து வந்தவை. அளவு × விகிதத்தில் இருப்பில் சேர்க்கப்படும், சராசரி விலை தானாகப் புதுப்பிக்கப்படும். திரும்பப் பெறுதலின்போது கண்டறிய சப்ளையரின் லாட் எண்ணைப் பதிவு செய்யுங்கள்.",
  "Supplier bill no. (optional)": "சப்ளையர் பில் எண் (விருப்பம்)",
  "Supplier lot no.": "சப்ளையர் லாட் எண்",
  "Supplier lot": "சப்ளையர் லாட்",
  "Rate ₹ per": "விகிதம் ₹ ஒவ்வொரு",
  "+ Add item": "+ பொருளைச் சேர்",
  "Post receipt": "ரசீதைப் பதிவு செய்",
  // ---------- batch card ----------
  "One card per batch: issue what was really used, then record what it made. A posted batch is never edited; a mistake is corrected with a reversal.":
    "ஒரு தொகுப்புக்கு ஓர் அட்டை: உண்மையில் பயன்படுத்தியதை வழங்குங்கள், பிறகு அது தயாரித்ததைப் பதிவு செய்யுங்கள். பதிவு செய்த தொகுப்பு ஒருபோதும் திருத்தப்படாது; தவறு எதிர்ப்பதிவால் சரிசெய்யப்படும்.",
  "Start a batch": "தொகுப்பைத் தொடங்கு",
  "Product and pack": "பொருள் மற்றும் பொதி",
  "Start batch": "தொகுப்பைத் தொடங்கு",
  "Batches in progress": "நடைபெறும் தொகுப்புகள்",
  "1. Materials used": "1. பயன்படுத்திய பொருட்கள்",
  "2. What the batch made": "2. தொகுப்பு தயாரித்தவை",
  "Issued so far": "இதுவரை வழங்கியது",
  "In store → after": "கிடங்கில் → பிறகு",
  "Issue materials": "பொருட்களை வழங்கு",
  "Good packets (expected": "நல்ல பாக்கெட்டுகள் (எதிர்பார்ப்பு",
  "Damaged pouches": "சேதமடைந்த பைகள்",
  "Cartons used": "பயன்படுத்திய அட்டைப்பெட்டிகள்",
  "Seal failure": "அடைப்புத் தோல்வி",
  "Torn pouch": "கிழிந்த பை",
  "Print error": "அச்சுப் பிழை",
  "Under weight": "குறைந்த எடை",
  Other: "மற்றவை",
  "Oil and fill-weight samples (optional)": "எண்ணெய் மற்றும் நிரப்பு எடை மாதிரிகள் (விருப்பம்)",
  "Fresh oil, L": "புதிய எண்ணெய், L",
  "Top-ups, L": "கூடுதல் சேர்ப்பு, L",
  "TPC %": "TPC %",
  "Net weights sampled, g (for example 203, 201, 205)":
    "மாதிரி நிகர எடைகள், g (உதாரணமாக 203, 201, 205)",
  "Post batch": "தொகுப்பைப் பதிவு செய்",
  "cooking oil used, L": "பயன்படுத்திய சமையல் எண்ணெய், L",
  "flour used, kg": "பயன்படுத்திய மாவு, kg",
  "spice mix used, kg": "பயன்படுத்திய மசாலா கலவை, kg",
  "Where did this batch's money go? →": "இந்தத் தொகுப்பின் பணம் எங்கே போனது? →",
  // ---------- run costs ----------
  "Labour and gas / power for a finished batch. They are added to the batch's packets wherever those packets are now, so the cost per packet is complete.":
    "முடிந்த தொகுப்புக்கான கூலி மற்றும் எரிவாயு / மின்சாரம். அந்தப் பாக்கெட்டுகள் இப்போது எங்கிருந்தாலும் அவற்றில் சேர்க்கப்படும், அதனால் ஒரு பாக்கெட்டின் செலவு முழுமையாகும்.",
  "Labour and gas": "கூலி மற்றும் எரிவாயு",
  "Labour ₹": "கூலி ₹",
  "Gas / power ₹": "எரிவாயு / மின்சாரம் ₹",
  "Add costs": "செலவுகளைச் சேர்",
  "Mark costs final": "செலவுகளை இறுதி எனக் குறி",
  "Per good packet": "ஒரு நல்ல பாக்கெட்டுக்கு",
  "Margin per packet": "ஒரு பாக்கெட்டின் லாப வரம்பு",
  "Costs added. The cost per packet below now includes them.":
    "செலவுகள் சேர்க்கப்பட்டன. கீழே உள்ள ஒரு பாக்கெட்டின் செலவில் அவை இப்போது அடங்கும்.",
  "Costs are final for this batch.": "இந்தத் தொகுப்பின் செலவுகள் இறுதியானவை.",
  // ---------- planner, runway, brief ----------
  "What the stock allows, what to make next and what to buy. It only recommends: approving creates a":
    "இருப்பு எதை அனுமதிக்கிறது, அடுத்து என்ன செய்வது, என்ன வாங்குவது. இது பரிந்துரை மட்டுமே: ஒப்புதல் அளித்தால் உருவாவது ஒரு",
  ", nothing is posted.": ", எதுவும் பதிவு செய்யப்படாது.",
  "Material runway": "பொருள் இருப்புக் காலம்",
  "Batches it allows": "அனுமதிக்கும் தொகுப்புகள்",
  "Per batch": "ஒரு தொகுப்புக்கு",
  "Next production day": "அடுத்த உற்பத்தி நாள்",
  "Room for": "இடம்:",
  "batches a day. The planner makes the most order value the materials and the day allow (":
    "தொகுப்புகள் ஒரு நாளில். பொருட்களும் நாளும் அனுமதிக்கும் அதிகபட்ச ஆர்டர் மதிப்பைத் திட்டமிடல் உருவாக்குகிறது (",
  "best plan found": "சிறந்த திட்டம் கிடைத்தது",
  "nothing to plan today": "இன்று திட்டமிட எதுவும் இல்லை",
  "Still to supply": "இன்னும் வழங்க வேண்டியது",
  "still to supply": "இன்னும் வழங்க வேண்டியது",
  "Covered by this plan": "இந்தத் திட்டம் உள்ளடக்கியது",
  "Order value this plan supplies:": "இந்தத் திட்டம் வழங்கும் ஆர்டர் மதிப்பு:",
  "What to buy": "என்ன வாங்குவது",
  "Nothing to buy: stock covers the orders and the reorder levels.":
    "வாங்க எதுவும் இல்லை: இருப்பு ஆர்டர்களையும் மறு ஆர்டர் நிலைகளையும் ஈடுகட்டுகிறது.",
  "Create draft batch": "வரைவுத் தொகுப்பை உருவாக்கு",
  "Create draft purchase order": "வரைவுக் கொள்முதல் ஆர்டரை உருவாக்கு",
  "no batches": "தொகுப்புகள் இல்லை",
  "Up to": "அதிகபட்சம்",
  "Five cards, then today’s three actions, biggest rupee impact first. Tap ⓘ on any number to see how it is worked out.":
    "ஐந்து அட்டைகள், பிறகு இன்றைய மூன்று செயல்கள், அதிக ரூபாய் தாக்கம் முதலில். எப்படிக் கணக்கிடப்பட்டது என்று பார்க்க எந்த எண்ணிலும் ⓘ-ஐத் தட்டவும்.",
  "· Five cards, then today’s three actions, biggest rupee impact first. Tap ⓘ on any number to see how it is worked out.":
    "· ஐந்து அட்டைகள், பிறகு இன்றைய மூன்று செயல்கள், அதிக ரூபாய் தாக்கம் முதலில். எப்படிக் கணக்கிடப்பட்டது என்று பார்க்க எந்த எண்ணிலும் ⓘ-ஐத் தட்டவும்.",
  "Today’s 3 actions": "இன்றைய 3 செயல்கள்",
  "Today’s orders": "இன்றைய ஆர்டர்கள்",
  "dated today, worth": "இன்றைய தேதியில், மதிப்பு",
  "waiting for a decision (": "முடிவுக்காகக் காத்திருக்கின்றன (",
  "Open the order inbox": "ஆர்டர் பெட்டியைத் திற",
  "Available vs pending": "கிடைப்பது மற்றும் நிலுவை ஆர்டர்கள்",
  "available,": "கிடைக்கிறது,",
  "Open the batch planner": "தொகுப்புத் திட்டமிடலைத் திற",
  "All batches": "அனைத்துத் தொகுப்புகள்",
  "in full from stock; runs out first:": "இருப்பிலிருந்து முழுமையாக; முதலில் தீர்வது:",
  "in full. Runs out first:": "முழுமையாக. முதலில் தீர்வது:",
  "See every material": "அனைத்துப் பொருட்களையும் பார்",
  "Money to collect": "வசூலிக்க வேண்டிய பணம்",
  "Open collections": "வசூலைத் திற",
  "Orders waiting for a decision": "முடிவுக்காகக் காத்திருக்கும் ஆர்டர்கள்",
  // ---------- trace, freshness, food safety ----------
  "Pick a batch or a supplier lot: where it came from, where every packet went, and what a recall would reach. Read-only.":
    "ஒரு தொகுப்பையோ சப்ளையர் லாட்டையோ தேர்ந்தெடுங்கள்: அது எங்கிருந்து வந்தது, ஒவ்வொரு பாக்கெட்டும் எங்கே சென்றது, திரும்பப் பெறுதல் எதுவரை செல்லும். படிக்க மட்டும்.",
  "Lot or batch number": "லாட் அல்லது தொகுப்பு எண்",
  "Lots found": "கண்டறிந்த லாட்டுகள்",
  "Last 30 days, from what each batch recorded when it was completed. Thresholds are DEMO settings: check them before real use.":
    "கடந்த 30 நாட்கள், ஒவ்வொரு தொகுப்பும் முடிந்தபோது பதிவு செய்தவற்றிலிருந்து. வரம்புகள் DEMO அமைப்புகள்: உண்மையான பயன்பாட்டுக்கு முன் சரிபாருங்கள்.",
  "Frying oil": "பொரிக்கும் எண்ணெய்",
  "Oil used": "பயன்படுத்திய எண்ணெய்",
  "Top-ups": "கூடுதல் சேர்ப்பு",
  TPC: "TPC",
  Discarded: "கழிக்கப்பட்டது",
  discard: "கழி",
  "Fill weights": "நிரப்பு எடைகள்",
  "Samples (g)": "மாதிரிகள் (g)",
  "Mean net": "சராசரி நிகர எடை",
  "Over declared": "அறிவித்ததை விட அதிகம்",
  Giveaway: "அதிகமாகக் கொடுத்தது",
  "Short fills": "குறை நிரப்புகள்",
  "under 50 L on every day": "ஒவ்வொரு நாளும் 50 L-க்குக் கீழ்",
  "DEMO values: verify the tolerance table with a Legal Metrology officer before real use.":
    "DEMO மதிப்புகள்: உண்மையான பயன்பாட்டுக்கு முன் அனுமதி அட்டவணையை எடையளவியல் அலுவலருடன் சரிபாருங்கள்.",
  "DEMO settings: daily used-oil records are required above 50 L a day; oil with total polar compounds above 25% must be discarded.":
    "DEMO அமைப்புகள்: நாளொன்றுக்கு 50 L-க்கு மேல் பயன்படுத்திய எண்ணெய்க்குத் தினசரிப் பதிவு தேவை; மொத்த முனைவுச் சேர்மங்கள் 25%-க்கு மேல் உள்ள எண்ணெயைக் கழிக்க வேண்டும்.",
  // ---------- where profit leaks ----------
  "WHERE PROFIT LEAKS": "லாபம் எங்கே கசிகிறது",
  "Pick a completed batch to see where its cost went above or below the standard.":
    "செலவு தரநிலைக்கு மேலோ கீழோ எங்கே போனது என்று பார்க்க ஒரு முடிந்த தொகுப்பைத் தேர்ந்தெடுங்கள்.",
  "RUN COST": "தொகுப்புச் செலவு",
  "COST PER GOOD PACKET": "ஒரு நல்ல பாக்கெட்டின் செலவு",
  "STANDARD FOR THE GOOD PACKETS": "நல்ல பாக்கெட்டுகளுக்கான தரநிலை",
  "LEAK AGAINST STANDARD": "தரநிலையை விடக் கசிவு",
  "Run cost": "தொகுப்புச் செலவு",
  "Standard for the good packets": "நல்ல பாக்கெட்டுகளுக்கான தரநிலை",
  "Where the money went": "பணம் எங்கே போனது",
  "▲ Costs more": "▲ அதிகச் செலவு",
  "▼ Saves": "▼ சேமிப்பு",
  "⏳ Cost provisional": "⏳ செலவு தற்காலிகம்",
  "Checks to make": "செய்ய வேண்டிய சரிபார்ப்புகள்",
  "Possibilities to verify on the floor, not findings.":
    "தொழிற்சாலையில் சரிபார்க்க வேண்டிய சாத்தியங்கள், முடிவுகள் அல்ல.",
  "Valuation method comparison": "மதிப்பீட்டு முறை ஒப்பீடு",
  "Book value": "கணக்கு மதிப்பு",
  WAC: "WAC",
  FIFO: "FIFO",
  LAST: "கடைசி விலை",
  Last: "கடைசி",
  "Direct cost only: monthly overheads (rent, salaries) are not added to batches.":
    "நேரடிச் செலவு மட்டும்: மாதாந்திர மேல்செலவுகள் (வாடகை, சம்பளம்) தொகுப்புகளில் சேர்க்கப்படுவதில்லை.",
  "Check the purchase price of flour against the standard rate.":
    "மாவின் கொள்முதல் விலையைத் தரநிலை விகிதத்துடன் ஒப்பிட்டுச் சரிபாருங்கள்.",
  "conversion spend": "மாற்றுச் செலவு",
  "flour price": "மாவு விலை",
  "cooking oil usage": "சமையல் எண்ணெய் பயன்பாடு",
  "Saved against standard": "தரநிலையை விடச் சேமிப்பு",
  // ---------- reports ----------
  "Registers, stock, production, ageing, GST and the month-end close. Every number is read from posted records; every row opens its source document.":
    "பதிவேடுகள், இருப்பு, உற்பத்தி, நிலுவை வயது, GST மற்றும் மாத இறுதி முடிப்பு. ஒவ்வொரு எண்ணும் பதிவு செய்த ஆவணங்களிலிருந்து படிக்கப்படுகிறது; ஒவ்வொரு வரியும் அதன் மூல ஆவணத்தைத் திறக்கும்.",
  "Reports sections": "அறிக்கைப் பிரிவுகள்",
  Report: "அறிக்கை",
  GST: "GST",
  "Close month": "மாதத்தை முடி",
  Evidence: "ஆதாரம்",
  CSV: "CSV",
  Excel: "Excel",
  "Print / PDF": "அச்சிடு / PDF",
  "Sales register (by customer and product, net of credit notes)":
    "விற்பனைப் பதிவேடு (வாடிக்கையாளர் மற்றும் பொருள் வாரியாக, கடன் குறிப்புகள் கழித்து)",
  "Purchase register": "கொள்முதல் பதிவேடு",
  "Stock summary (opening, in, out, closing by quantity and value)":
    "இருப்புச் சுருக்கம் (தொடக்கம், வரவு, செலவு, இறுதி, அளவு மற்றும் மதிப்பு வாரியாக)",
  "Production report (planned vs actual, yield, waste, variance in rupees)":
    "உற்பத்தி அறிக்கை (திட்டமிட்டது மற்றும் உண்மை, விளைச்சல், கழிவு, ரூபாயில் வேறுபாடு)",
  "Receivables ageing (0-15, 16-45, 46-90, 90+, MSME 45-day marker)":
    "வரவேண்டியவற்றின் வயது (0-15, 16-45, 46-90, 90+, MSME 45 நாள் குறி)",
  "Stock and book-debts statement for the bank (drawing power)":
    "வங்கிக்கான இருப்பு மற்றும் கடனாளிகள் அறிக்கை (எடுக்கும் திறன்)",
  "Stock and book-debts statement (drawing power)":
    "இருப்பு மற்றும் கடனாளிகள் அறிக்கை (எடுக்கும் திறன்)",
  "GST summary for a month (GSTR-1 tables 4A, 5, 7, 9B, 12, 13 and GSTR-3B 3.1)":
    "ஒரு மாதத்துக்கான GST சுருக்கம் (GSTR-1 அட்டவணைகள் 4A, 5, 7, 9B, 12, 13 மற்றும் GSTR-3B 3.1)",
  "Tally XML (sales vouchers)": "Tally XML (விற்பனை வவுச்சர்கள்)",
  "GSTR-1 file (JSON, for review)": "GSTR-1 கோப்பு (JSON, மதிப்பாய்வுக்கு)",
  "The GSTR-1 file is shaped like the portal's offline tool for your chartered accountant to review. Nothing is filed or sent.":
    "GSTR-1 கோப்பு உங்கள் பட்டயக் கணக்காளர் மதிப்பாய்வு செய்ய போர்ட்டலின் ஆஃப்லைன் கருவி வடிவத்தில் உள்ளது. எதுவும் தாக்கல் செய்யப்படவோ அனுப்பப்படவோ இல்லை.",
  "Posted invoices and credit notes of the month; cancelled invoices appear in table 13 only.":
    "மாதத்தின் பதிவு செய்த விலைப்பட்டியல்களும் கடன் குறிப்புகளும்; ரத்து செய்த விலைப்பட்டியல்கள் அட்டவணை 13-இல் மட்டும் தோன்றும்.",
  "For review with your chartered accountant. Nothing is filed or sent to the GST portal.":
    "உங்கள் பட்டயக் கணக்காளருடன் மதிப்பாய்வுக்கு. GST போர்ட்டலுக்கு எதுவும் தாக்கல் செய்யப்படவோ அனுப்பப்படவோ இல்லை.",
  "B2B: registered buyers": "B2B: பதிவு பெற்ற வாங்குநர்கள்",
  "B2CL: unregistered, inter-state, large": "B2CL: பதிவு பெறாதவர்கள், மாநிலங்களுக்கிடையே, பெரியவை",
  "B2CS: unregistered, others": "B2CS: பதிவு பெறாதவர்கள், மற்றவை",
  "Credit notes to registered buyers (CDNR)":
    "பதிவு பெற்ற வாங்குநர்களுக்கான கடன் குறிப்புகள் (CDNR)",
  "Credit notes to unregistered buyers (CDNUR)":
    "பதிவு பெறாத வாங்குநர்களுக்கான கடன் குறிப்புகள் (CDNUR)",
  "Outward taxable supplies (net of credit notes)":
    "வெளிச்செல்லும் வரிக்குரிய விநியோகங்கள் (கடன் குறிப்புகள் கழித்து)",
  "Before you close": "முடிப்பதற்கு முன்",
  "Close the month": "மாதத்தை முடி",
  "Audit chain intact": "தணிக்கைச் சங்கிலி முழுமையாக உள்ளது",
  "Invoices add up to their headers": "விலைப்பட்டியல்கள் அவற்றின் தலைப்புகளுடன் கூடுகின்றன",
  "No store promises more stock than it holds":
    "எந்தக் கிடங்கும் தன்னிடம் உள்ளதைவிட அதிக இருப்பை வாக்களிக்கவில்லை",
  "Stock balances rebuild identically from the ledger":
    "இருப்பு நிலுவைகள் பேரேட்டிலிருந்து அப்படியே மீண்டும் உருவாகின்றன",
  "Law 1 quantity: every stock journal balances":
    "விதி 1 அளவு: ஒவ்வொரு இருப்புப் பதிவும் சமநிலையில்",
  "Law 2 value: every batch's lots = materials + run costs":
    "விதி 2 மதிப்பு: ஒவ்வொரு தொகுப்பின் லாட்டுகள் = பொருட்கள் + தொகுப்புச் செலவுகள்",
  "Law 3 mass: every batch reconciles, gaps disclosed":
    "விதி 3 எடை: ஒவ்வொரு தொகுப்பும் சரிசெய்யப்படுகிறது, இடைவெளிகள் வெளிப்படுத்தப்படுகின்றன",
  "Law 4 tax: invoice tax lines = GST summary = export":
    "விதி 4 வரி: விலைப்பட்டியல் வரி வரிகள் = GST சுருக்கம் = ஏற்றுமதிக் கோப்பு",
  "Batches started but not completed": "தொடங்கியும் முடிக்கப்படாத தொகுப்புகள்",
  "Completed batches whose run costs are not final":
    "தொகுப்புச் செலவுகள் இறுதியாகாத முடிந்த தொகுப்புகள்",
  "Invoices of the month not fully dispatched":
    "முழுமையாக அனுப்பப்படாத மாதத்தின் விலைப்பட்டியல்கள்",
  "Customers with overdue invoices": "காலம் கடந்த விலைப்பட்டியல்கள் உள்ள வாடிக்கையாளர்கள்",
  "Customers holding an unallocated advance": "ஒதுக்கப்படாத முன்பணம் வைத்துள்ள வாடிக்கையாளர்கள்",
  "Batches with a mass gap above tolerance (shown, not hidden)":
    "அனுமதிக்கு மேல் எடை இடைவெளி உள்ள தொகுப்புகள் (மறைக்காமல் காட்டப்படுகிறது)",
  "Approved orders not yet invoiced": "இன்னும் விலைப்பட்டியல் இடாத ஒப்புதல் பெற்ற ஆர்டர்கள்",
  "Download the Evidence Pack (ZIP)": "ஆதாரத் தொகுப்பைப் பதிவிறக்கு (ZIP)",
  "The pack holds every report, the GSTR-1 file, every stock movement, the audit-chain check with its head hash, the integrity results and the assumptions.":
    "இந்தத் தொகுப்பில் ஒவ்வொரு அறிக்கையும், GSTR-1 கோப்பும், ஒவ்வொரு இருப்பு நகர்வும், தணிக்கைச் சங்கிலிச் சரிபார்ப்பும், நேர்மை முடிவுகளும், அனுமானங்களும் உள்ளன.",
  "Tap Open on any row to see the document behind it.":
    "பின்னால் உள்ள ஆவணத்தைப் பார்க்க எந்த வரியிலும் திற என்பதைத் தட்டவும்.",
  "Raw materials": "மூலப்பொருட்கள்",
  "Finished goods": "முடிந்த பொருட்கள்",
  "Work in progress": "நடைபெறும் வேலை",
  "Drawing power": "எடுக்கும் திறன்",
  "Margin %": "மார்ஜின் %",
  "Book debts up to 90 days": "90 நாட்கள் வரையிலான கடனாளிகள்",
  "Book debts over 90 days (not eligible)": "90 நாட்களுக்கு மேலான கடனாளிகள் (தகுதியில்லை)",
  "Margins are DEMO settings; use the figures in your bank's sanction letter.":
    "மார்ஜின்கள் DEMO அமைப்புகள்; உங்கள் வங்கியின் அனுமதிக் கடிதத்தில் உள்ள எண்களைப் பயன்படுத்துங்கள்.",
  "Stock at book value (weighted average for raw materials, actual batch cost for finished goods).":
    "கணக்கு மதிப்பில் இருப்பு (மூலப்பொருட்களுக்கு எடையிட்ட சராசரி, முடிந்த பொருட்களுக்கு உண்மையான தொகுப்புச் செலவு).",
  "Ordered, not invoiced:": "ஆர்டர் செய்தது, விலைப்பட்டியல் இடாதது:",
  // ---------- settings ----------
  "A change applies from the date you pick. Anything already posted keeps the value it was made with, so the past never changes.":
    "நீங்கள் தேர்ந்தெடுக்கும் தேதியிலிருந்து மாற்றம் பொருந்தும். ஏற்கனவே பதிவு செய்தவை அப்போதைய மதிப்பையே வைத்திருக்கும், அதனால் கடந்தது ஒருபோதும் மாறாது.",
  Setting: "அமைப்பு",
  "New value": "புதிய மதிப்பு",
  "not set": "அமைக்கப்படவில்லை",
  "GST rates": "GST விகிதங்கள்",
  "Add a GST rate": "GST விகிதத்தைச் சேர்",
  "Add GST rate": "GST விகிதத்தைச் சேர்",
  "The rate before it ends the day before; invoices already posted keep their rate. Check rates with a chartered accountant (DEMO values).":
    "முந்தைய விகிதம் அதற்கு முந்தைய நாளில் முடியும்; ஏற்கனவே பதிவு செய்த விலைப்பட்டியல்கள் தங்கள் விகிதத்தை வைத்திருக்கும். விகிதங்களைப் பட்டயக் கணக்காளருடன் சரிபாருங்கள் (DEMO மதிப்புகள்).",
  "Variance flag above": "இதற்கு மேல் வேறுபாட்டைக் குறி",
  "Freshness alert after": "இதற்குப் பின் புத்துணர்ச்சி எச்சரிக்கை",
  "Used-oil (RUCO) threshold": "பயன்படுத்திய எண்ணெய் (RUCO) வரம்பு",
  "Frying oil TPC limit": "பொரிக்கும் எண்ணெய் TPC வரம்பு",
  "Shortage look-back": "பற்றாக்குறை பின்னோக்கு",
  "Batches per day": "நாளொன்றுக்குத் தொகுப்புகள்",
  "GSTR-1 B2CL threshold": "GSTR-1 B2CL வரம்பு",
  "E-way bill threshold, interstate": "E-way bill வரம்பு, மாநிலங்களுக்கிடையே",
  "E-way bill threshold, within the state": "E-way bill வரம்பு, மாநிலத்துக்குள்",
  "Bank margin on stock": "இருப்பின் மீதான வங்கி மார்ஜின்",
  "Bank margin on debtors": "கடனாளிகள் மீதான வங்கி மார்ஜின்",
  "Road distance factor": "சாலைத் தூரக் காரணி",
  "Diesel price": "டீசல் விலை",
  "CO₂ per km": "ஒரு கி.மீ.-க்கு CO₂",
  "Cost of credit": "கடனின் செலவு",
  "Backhaul detour allowed": "திரும்பும் வழியில் அனுமதிக்கப்பட்ட சுற்று",
  "times straight line": "நேர்கோட்டின் மடங்கு",
  "% a year": "% ஆண்டுக்கு",
  "L/day": "L/நாள்",
  "kg/km": "kg/கி.மீ.",
  INR: "₹",
  "INR/L": "₹/L",
  // ---------- sample-day check ----------
  "One sample working day (a purchase, a batch, two orders, an invoice, a payment and the batch costs) is replayed through the real system on a separate practice factory, and 26 figures are checked against the values they must have. The DEMO factory and your own factory are never touched.":
    "ஒரு மாதிரி வேலை நாள் (ஒரு கொள்முதல், ஒரு தொகுப்பு, இரண்டு ஆர்டர்கள், ஒரு விலைப்பட்டியல், ஒரு பணம் மற்றும் தொகுப்புச் செலவுகள்) தனிப் பயிற்சித் தொழிற்சாலையில் உண்மையான அமைப்பின் வழியே மீண்டும் இயக்கப்பட்டு, 26 எண்கள் அவை இருக்க வேண்டிய மதிப்புகளுடன் சரிபார்க்கப்படுகின்றன. DEMO தொழிற்சாலையும் உங்கள் தொழிற்சாலையும் ஒருபோதும் தொடப்படுவதில்லை.",
  "Run the check now": "இப்போதே சரிபார்",
  "The day, step by step": "அந்த நாள், படிப்படியாக",
  "see it in the tour": "சுற்றுலாவில் பார்",
  "Where to see it": "எங்கே பார்ப்பது",
  "Sign in as the DEMO Factory admin or Owner":
    "DEMO தொழிற்சாலை நிர்வாகி அல்லது உரிமையாளராக உள்நுழையுங்கள்",
  "to run it again.": "மீண்டும் இயக்க.",
  "Flour WAC after purchase": "கொள்முதலுக்குப் பின் மாவின் சராசரி விலை",
  "Flour closing": "இறுதி மாவு",
  "Oil closing": "இறுதி எண்ணெய்",
  "Pouches closing": "இறுதிப் பைகள்",
  "Spice closing / cartons closing": "இறுதி மசாலா / இறுதி அட்டைப்பெட்டிகள்",
  "Finished goods after run": "தொகுப்புக்குப் பின் முடிந்த பொருட்கள்",
  "Finished goods after Retailer A dispatch":
    "சில்லறை வியாபாரி A-க்கு அனுப்பிய பின் முடிந்த பொருட்கள்",
  "Yield variance (flagged)": "விளைச்சல் வேறுபாடு (குறிக்கப்பட்டது)",
  "Oil variance (flagged)": "எண்ணெய் வேறுபாடு (குறிக்கப்பட்டது)",
  "Pouch flexible variance (flagged)": "பை நெகிழ் வேறுபாடு (குறிக்கப்பட்டது)",
  "Retailer A invoice taxable value": "சில்லறை வியாபாரி A விலைப்பட்டியல் வரிக்குரிய மதிப்பு",
  "Retailer A CGST": "சில்லறை வியாபாரி A CGST",
  "Retailer A SGST": "சில்லறை வியாபாரி A SGST",
  "Retailer A invoice total": "சில்லறை வியாபாரி A விலைப்பட்டியல் மொத்தம்",
  "Retailer A outstanding": "சில்லறை வியாபாரி A நிலுவை",
  "Distributor B shortage flagged, no negative stock, not invoiced":
    "விநியோகஸ்தர் B பற்றாக்குறை குறிக்கப்பட்டது, எதிர்மறை இருப்பு இல்லை, விலைப்பட்டியல் இடப்படவில்லை",
  "Distributor B tax regime": "விநியோகஸ்தர் B வரி முறை",
  "Value conservation of the run": "தொகுப்பின் மதிப்புப் பாதுகாப்பு",
  "Variance waterfall sums exactly": "வேறுபாட்டுப் படிக்கட்டு சரியாகக் கூடுகிறது",
  "Variance waterfall, largest first": "வேறுபாட்டுப் படிக்கட்டு, பெரியது முதலில்",
  "Cost per good packet + sensitivity": "ஒரு நல்ல பாக்கெட்டின் செலவு + உணர்திறன்",
  "FEFO dispatch to Retailer A": "சில்லறை வியாபாரி A-க்கு FEFO அனுப்புதல்",
  "Shortage attribution": "பற்றாக்குறைக் காரணம்",
  "e-Way Bill for B not required": "B-க்கு e-Way Bill தேவையில்லை",
  "Integrity: 4 conservation laws, balance rebuild, audit chain":
    "நேர்மை: 4 பாதுகாப்பு விதிகள், நிலுவை மறுகட்டமைப்பு, தணிக்கைச் சங்கிலி",
  "IGST · 300.00 · 220.00": "IGST · 300.00 · 220.00",
  // ---------- explain popover, misc ----------
  "Explain this number": "இந்த எண்ணை விளக்கு",
  FORMULA: "சூத்திரம்",
  Formula: "சூத்திரம்",
  METHOD: "முறை",
  "from the production run": "உற்பத்தித் தொகுப்பிலிருந்து",
  "from the stock movement": "இருப்பு நகர்விலிருந்து",
  "from the stock balance": "இருப்பு நிலுவையிலிருந்து",
  "from the purchase receipt": "கொள்முதல் ரசீதிலிருந்து",
  "from the run cost entry": "தொகுப்புச் செலவுப் பதிவிலிருந்து",
  "from the standard cost card": "தரநிலைச் செலவு அட்டையிலிருந்து",
  "from the invoice": "விலைப்பட்டியலிலிருந்து",
  "from the payment": "பணம் செலுத்துதலிலிருந்து",
  "run cost / good units": "தொகுப்புச் செலவு / நல்ல அலகுகள்",
  "run cost": "தொகுப்புச் செலவு",
  "good units": "நல்ல அலகுகள்",
  "Page not found": "பக்கம் கிடைக்கவில்லை",
  "Sign in to see": "பார்க்க உள்நுழையுங்கள்:",
  "This screen shows real data from the factory, so it needs a login. The DEMO logins are on the sign-in page.":
    "இந்தத் திரை தொழிற்சாலையின் உண்மையான தரவைக் காட்டுகிறது, அதனால் உள்நுழைவு தேவை. DEMO உள்நுழைவுகள் உள்நுழைவுப் பக்கத்தில் உள்ளன.",
  "Not part of your role": "உங்கள் பங்கில் இது இல்லை",
  // ---------- item and product words (also used inside patterns) ----------
  flour: "மாவு",
  "flour (kg)": "மாவு (kg)",
  "cooking oil": "சமையல் எண்ணெய்",
  "cooking oil (L)": "சமையல் எண்ணெய் (L)",
  "spice mix": "மசாலா கலவை",
  "spice mix (kg)": "மசாலா கலவை (kg)",
  "pouch 200g": "200g பை",
  "pouch 200g (piece)": "200g பை (துண்டு)",
  "pouch 500g": "500g பை",
  "carton 20": "அட்டைப்பெட்டி (20)",
  "carton 20 (piece)": "அட்டைப்பெட்டி (20) (துண்டு)",
  "murukku 200g": "முறுக்கு 200g",
  "DEMO murukku 200g": "DEMO முறுக்கு 200g",
  "DEMO Murukku 200 g": "DEMO முறுக்கு 200 கி",
  "DEMO Murukku 500 g": "DEMO முறுக்கு 500 கி",
  "Murukku 200 g": "முறுக்கு 200 கி",
  "Murukku 500 g": "முறுக்கு 500 கி",
  "yield loss Murukku 200 g": "விளைச்சல் இழப்பு முறுக்கு 200 கி",
  "carton 20 usage": "அட்டைப்பெட்டி (20) பயன்பாடு",
  "pouch 200g usage": "200g பை பயன்பாடு",
  "flour, pouch 200g": "மாவு, 200g பை",
  "+1 carton": "+1 அட்டைப்பெட்டி",
  "AaharOS Demo Snacks (DEMO)": "AaharOS Demo Snacks (DEMO)",
};

/** Words inside a pattern's captured text ("Change Diesel price", "cost-to-serve per packet, DEMO Retailer A"). */
function term(s: string): string {
  return TA[s] ?? s;
}

const n = (x: string) => x;

/** Sentences that carry numbers or names: [English pattern, Tamil builder]. Tried after the exact table. */
export const PATTERNS: [RegExp, (...m: string[]) => string][] = [
  [/^Explain this number: (.+)$/, (_, x) => `இந்த எண்ணை விளக்கு: ${term(x)}`],
  [/^Change (.+)$/, (_, x) => `மாற்று: ${term(x)}`],
  [/^(\d[\d,.]*) packets$/, (_, x) => `${n(x)} பாக்கெட்டுகள்`],
  [/^(\d[\d,.]*) packet$/, (_, x) => `${n(x)} பாக்கெட்`],
  [/^(\d[\d,.]*) batch(es)?$/, (_, x) => `${n(x)} தொகுப்பு`],
  [/^(\d[\d,.]*) pieces?$/, (_, x) => `${n(x)} துண்டுகள்`],
  [/^(\d+) damaged$/, (_, x) => `${x} சேதம்`],
  [/^All (\d[\d,]*) packets$/, (_, x) => `அனைத்து ${x} பாக்கெட்டுகளும்`],
  [/^The (\d[\d,]*) available now$/, (_, x) => `இப்போது கிடைக்கும் ${x}`],
  [
    /^In stock today \((\d[\d,]*) available\)$/,
    (_, x) => `இன்று இருப்பில் உள்ளது (${x} கிடைக்கிறது)`,
  ],
  [
    /^Only (\d[\d,]*) available today \(partial\)$/,
    (_, x) => `இன்று ${x} மட்டுமே கிடைக்கும் (பகுதி)`,
  ],
  [
    /^Selling price (₹[\d,.]+) ex-tax · ([\d.]+)% of the price$/,
    (_, p, m) => `விற்பனை விலை ${p} வரிக்கு முன் · விலையில் ${m}%`,
  ],
  [/^Stop (\d+)$/, (_, x) => `நிறுத்தம் ${x}`],
  [/^Decide (\d+) waiting orders?$/, (_, x) => `காத்திருக்கும் ${x} ஆர்டரை முடிவு செய்யுங்கள்`],
  [
    /^Start (\d+) batch(?:es)? of (.+) today$/,
    (_, x, p) => `இன்று ${term(p)} ${x} தொகுப்பைத் தொடங்குங்கள்`,
  ],
  [/^Check (.+) on batch (\S+)$/, (_, w, b) => `தொகுப்பு ${b}-இல் ${term(w)} சரிபாருங்கள்`],
  [/^(.+) · (B-\d+)$/, (_, w, b) => `${term(w)} · ${b}`],
  [/^yield loss (.+)$/, (_, p) => `விளைச்சல் இழப்பு ${term(p)}`],
  [/^(.+) usage$/, (_, x) => `${term(x)} பயன்பாடு`],
  [/^(.+) usage · (\d+) damaged$/, (_, x, d) => `${term(x)} பயன்பாடு · ${d} சேதம்`],
  [/^(\d+) of (\d+) correct$/, (_, a, b) => `${b}-இல் ${a} சரி`],
  [/^running… (\d+) s$/, (_, s) => `இயங்குகிறது… ${s} வி`],
  [/^checked (.+)$/, (_, d) => `சரிபார்த்தது ${d}`],
  [
    /^Batch (B-\d+) posted: finished packets are in stock\.(?: Over the tolerance: (.+)\.)?$/,
    (_, b, f) =>
      `தொகுப்பு ${b} பதிவு செய்யப்பட்டது: முடிந்த பாக்கெட்டுகள் இருப்பில் உள்ளன.` +
      (f
        ? ` அனுமதிக்கு மேல்: ${f
            .replace(/cooking oil/, "சமையல் எண்ணெய்")
            .replace(/yield/, "விளைச்சல்")
            .replace(/pouch 200g/, "200g பை")}.`
        : ""),
  ],
  [
    /^Batch (B-\d+) started\. The recipe and pack are now frozen for this batch\.$/,
    (_, b) =>
      `தொகுப்பு ${b} தொடங்கியது. செய்முறையும் பொதியும் இந்தத் தொகுப்புக்கு இப்போது நிலைநிறுத்தப்பட்டன.`,
  ],
  [
    /^Materials issued on (\S+)\. Raw stock is down by exactly these quantities\.$/,
    (_, d) =>
      `பொருட்கள் ${d} மூலம் வழங்கப்பட்டன. மூலப்பொருள் இருப்பு சரியாக இந்த அளவுகளால் குறைந்தது.`,
  ],
  [/^Receipt (\S+) posted\.$/, (_, r) => `ரசீது ${r} பதிவு செய்யப்பட்டது.`],
  [/^(.+) average cost now$/, (_, x) => `${term(x)} சராசரி விலை இப்போது`],
  [
    /^Payment (\S+) recorded and allocated, oldest invoice first\.$/,
    (_, p) => `பணம் ${p} பதிவு செய்யப்பட்டு, பழைய விலைப்பட்டியலுக்கு முதலில் ஒதுக்கப்பட்டது.`,
  ],
  [/^✓ Dispatched as (\S+)\.$/, (_, d) => `✓ ${d} ஆக அனுப்பப்பட்டது.`],
  [/^Dispatched as (\S+)\.$/, (_, d) => `${d} ஆக அனுப்பப்பட்டது.`],
  [/^✓ approved (\d+) packets$/, (_, x) => `✓ ${x} பாக்கெட்டுகளுக்கு ஒப்புதல்`],
  [
    /^Saved: the new value applies from (\S+)\.$/,
    (_, d) => `சேமிக்கப்பட்டது: புதிய மதிப்பு ${d} முதல் பொருந்தும்.`,
  ],
  [
    /^Not needed: a delivery (within the state|to another state) worth (₹[\d,.]+) is not above the (₹[\d,.]+) limit \(Rule 138\)$/,
    (_, w, v, l) =>
      `தேவையில்லை: ${w === "within the state" ? "மாநிலத்துக்குள்" : "வேறு மாநிலத்துக்கு"} ${v} மதிப்பிலான விநியோகம் ${l} வரம்புக்கு மேல் இல்லை (விதி 138)`,
  ],
  [
    /^Needed: a delivery (within the state|to another state) worth (₹[\d,.]+) is above the (₹[\d,.]+) limit \(Rule 138\)$/,
    (_, w, v, l) =>
      `தேவை: ${w === "within the state" ? "மாநிலத்துக்குள்" : "வேறு மாநிலத்துக்கு"} ${v} மதிப்பிலான விநியோகம் ${l} வரம்புக்கு மேல் உள்ளது (விதி 138)`,
  ],
  [
    /^(.+): (\d[\d,.]*) packets from batch (\S+) \(cost (₹[\d,.]+)\)$/,
    (_, p, q, b, c) => `${term(p)}: தொகுப்பு ${b}-இலிருந்து ${q} பாக்கெட்டுகள் (செலவு ${c})`,
  ],
  [
    /^Cost of goods leaving: (₹[\d,.]+) · consignment value with tax (₹[\d,.]+)$/,
    (_, a, b) => `வெளியேறும் பொருட்களின் செலவு: ${a} · வரியுடன் சரக்கு மதிப்பு ${b}`,
  ],
  [/^(\d+) packets · (₹[\d,.]+) ex-tax$/, (_, q, v) => `${q} பாக்கெட்டுகள் · ${v} வரிக்கு முன்`],
  [
    /^(\S+) · (\d+) packets · (₹[\d,.]+) ex-tax$/,
    (_, o, q, v) => `${o} · ${q} பாக்கெட்டுகள் · ${v} வரிக்கு முன்`,
  ],
  [/^(\d+) packets · estimated, ex-tax$/, (_, q) => `${q} பாக்கெட்டுகள் · மதிப்பீடு, வரிக்கு முன்`],
  [/^Last time: (\d+) packets$/, (_, q) => `கடந்த முறை: ${q} பாக்கெட்டுகள்`],
  [
    /^✓ In stock today \((\d[\d,]*) available\)$/,
    (_, x) => `✓ இன்று இருப்பில் உள்ளது (${x} கிடைக்கிறது)`,
  ],
  [
    /^⚠ Only (\d[\d,]*) available today \(partial\)$/,
    (_, x) => `⚠ இன்று ${x} மட்டுமே கிடைக்கும் (பகுதி)`,
  ],
  [/^Retailer · (.+)$/, (_, s) => `சில்லறை வியாபாரி · ${term(s)}`],
  [/^Distributor · (.+)$/, (_, s) => `விநியோகஸ்தர் · ${term(s)}`],
  [/^HSN (\d+) at ([\d.]+)% \((.+) units\)$/, (_, h, r, q) => `HSN ${h} ${r}% (${q} அலகுகள்)`],
  [/^Send (\d+) now, backorder (\d+)$/, (_, a, b) => `இப்போது ${a} அனுப்பு, ${b} பின்னர்`],
  [
    /^Hold (\d+) packets now and backorder (\d+)\. The backorder is filled when stock arrives\.$/,
    (_, a, b) =>
      `இப்போது ${a} பாக்கெட்டுகளை ஒதுக்கி, ${b} பின்னர் வழங்கப்படும். இருப்பு வந்ததும் பின்னர் வழங்க வேண்டியது நிறைவேற்றப்படும்.`,
  ],
  [/^Approve all (\d+) packets$/, (_, a) => `அனைத்து ${a} பாக்கெட்டுகளையும் ஒப்புக்கொள்`],
  [
    /^Preview the dispatch of (\d+) packets$/,
    (_, a) => `${a} பாக்கெட்டுகளின் அனுப்புதலை முன்னோட்டம் பார்`,
  ],
  [/^(\d+) packets to dispatch$/, (_, a) => `அனுப்ப வேண்டிய ${a} பாக்கெட்டுகள்`],
  [/^Open (B-\d+) \((\S+)\)$/, (_, b, d) => `${b}-ஐத் திற (${d})`],
  [
    /^See where batch (B-\d+)'s money went →$/,
    (_, b) => `தொகுப்பு ${b}-இன் பணம் எங்கே போனது என்று பார் →`,
  ],
  [/^Batch (B-\d+)$/, (_, b) => `தொகுப்பு ${b}`],
  [
    /^(B-\d+) · (\S+) · (\d+) good packets · provisional$/,
    (_, b, d, q) => `${b} · ${d} · ${q} நல்ல பாக்கெட்டுகள் · தற்காலிகம்`,
  ],
  [
    /^(B-\d+) · (\S+) · (\d+) good packets · final$/,
    (_, b, d, q) => `${b} · ${d} · ${q} நல்ல பாக்கெட்டுகள் · இறுதி`,
  ],
  [
    /^Not enough (.+) in stock: (.+) available, (.+) needed\.$/,
    (_, i, a, w) => `இருப்பில் போதுமான ${term(i)} இல்லை: ${a} கிடைக்கிறது, ${w} தேவை.`,
  ],
  [
    /^Check fill weights, breakage and the process log for batch (\S+): fewer good packets were made than the bulk allowed\.$/,
    (_, b) =>
      `தொகுப்பு ${b}-க்கு நிரப்பு எடை, உடைவு மற்றும் செயல்முறைப் பதிவைச் சரிபாருங்கள்: மாவுக் கலவை அனுமதித்ததைவிடக் குறைவான நல்ல பாக்கெட்டுகள் தயாரிக்கப்பட்டன.`,
  ],
  [
    /^Check the issue slips and top-ups of (.+) for batch (\S+): more was used than the recipe needs\.$/,
    (_, i, b) =>
      `தொகுப்பு ${b}-க்கு ${term(i)} வழங்கல் சீட்டுகளையும் கூடுதல் சேர்ப்புகளையும் சரிபாருங்கள்: செய்முறைக்குத் தேவையானதைவிட அதிகம் பயன்படுத்தப்பட்டது.`,
  ],
  [
    /^Check the issue slips of (.+) for batch (\S+): less was used than the recipe needs\.$/,
    (_, i, b) =>
      `தொகுப்பு ${b}-க்கு ${term(i)} வழங்கல் சீட்டுகளைச் சரிபாருங்கள்: செய்முறைக்குத் தேவையானதைவிடக் குறைவாகப் பயன்படுத்தப்பட்டது.`,
  ],
  [
    /^Check sealing and handling of (.+) for batch (\S+) \((\d+) damaged\)\.$/,
    (_, i, b, d) =>
      `தொகுப்பு ${b}-க்கு ${term(i)} அடைப்பையும் கையாளுதலையும் சரிபாருங்கள் (${d} சேதம்).`,
  ],
  [
    /^Confirm the count of (.+) for batch (\S+): less was used than the standard\.$/,
    (_, i, b) =>
      `தொகுப்பு ${b}-க்கு ${term(i)} எண்ணிக்கையை உறுதிப்படுத்துங்கள்: தரநிலையைவிடக் குறைவாகப் பயன்படுத்தப்பட்டது.`,
  ],
  [
    /^Check labour hours and gas readings for batch (\S+) against the standard\.$/,
    (_, b) =>
      `தொகுப்பு ${b}-க்கு கூலி நேரங்களையும் எரிவாயு அளவீடுகளையும் தரநிலையுடன் ஒப்பிட்டுச் சரிபாருங்கள்.`,
  ],
  [
    /^Check the purchase price of (.+) against the standard rate\.$/,
    (_, i) => `${term(i)} கொள்முதல் விலையைத் தரநிலை விகிதத்துடன் ஒப்பிட்டுச் சரிபாருங்கள்.`,
  ],
  [
    /^No purchase yet for (.+): book value used\.$/,
    (_, i) =>
      `${i.split(", ").map(term).join(", ")} - இன்னும் கொள்முதல் இல்லை: கணக்கு மதிப்பு பயன்படுத்தப்பட்டது.`,
  ],
  [/^(₹[\d,.]+) \/ packet$/, (_, v) => `${v} / பாக்கெட்`],
  [/^(₹[\d,.]+) \/ kg$/, (_, v) => `${v} / kg`],
  [/^(\d+)-Tamil Nadu$/, (_, c) => `${c}-தமிழ்நாடு`],
  [/^(\d+)-Karnataka$/, (_, c) => `${c}-கர்நாடகா`],
  [/^(\d+) from (B-\d+|OPEN-LOT)$/, (_, q, b) => `${b}-இலிருந்து ${q}`],
  [/^· best before (\S+)$/, (_, d) => `· காலாவதி ${d}`],
  [/^· month (\S+)$/, (_, d) => `· மாதம் ${d}`],
  [/^\(likely (\d+), at least (\d+)\)$/, (_, a, b) => `(சுமார் ${a}, குறைந்தது ${b})`],
  [/^(\d+) below (\d+) g$/, (_, a, b) => `${b} g-க்குக் கீழ் ${a}`],
  [
    /^Invoices for outward supply: (\S+) to (\S+) \((\d+) cancelled\)$/,
    (_, a, b, c) => `வெளிச்செல்லும் விநியோக விலைப்பட்டியல்கள்: ${a} முதல் ${b} வரை (${c} ரத்து)`,
  ],
  [/^(\d+) steps$/, (_, x) => `${x} படிகள்`],
];

// The tour's step titles and "why it matters" lines also appear outside the tour (the sample-day check, the finish
// panel), so their Tamil comes from the tour's own Tamil text.
for (const step of STEPS) {
  const ta = STEPS_TA[step.id];
  if (!ta) continue;
  TA[step.title] ??= ta.title;
  TA[step.why] ??= ta.why;
  TA[step.who.login] ??= ta.login;
}
