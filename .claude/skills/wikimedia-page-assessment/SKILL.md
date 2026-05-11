## 🛠 Skill: Querying Wikipedia Page Assessments

### **Description**

Enables the agent to retrieve quality and importance ratings for Wikipedia articles. This data is derived from WikiProject banners on talk pages and is stored in the `page_assessments` table.

### **Database Schema: `enwiki_p**`

The assessment system relies on three primary tables:

1. **`page_assessments`**: Links page IDs to assessment values.
2. **`page_assessments_projects`**: Maps `pa_project_id` to human-readable WikiProject names (e.g., "Architecture", "Medicine").
3. **`page`**: Necessary to resolve `pa_page_id` into the actual article `page_title`.

### **Core Data Model**

* **`pa_class`**: Quality grade. Standard values: `FA` (Featured), `GA` (Good), `B`, `C`, `Start`, `Stub`, `List`.
* **`pa_importance`**: Priority for a project. Standard values: `Top`, `High`, `Mid`, `Low`, `NA`.

### **Standard Implementation Pattern**

```sql
SELECT 
    p.page_title, 
    pap.pap_project_title AS wikiproject,
    pa.pa_class, 
    pa.pa_importance
FROM page_assessments pa
JOIN page_assessments_projects pap ON pa.pa_project_id = pap.pap_project_id
JOIN page p ON pa.pa_page_id = p.page_id
WHERE p.page_title = 'YOUR_PAGE_TITLE' -- Replace spaces with underscores
  AND p.page_namespace = 0;

```

### **Constraint & Analysis Guardrails**

1. **Talk Page Paradox:** Assessment templates exist on **Talk pages** (Namespace 1), but the `pa_page_id` refers to the **Subject page** (Namespace 0). Always join with the Subject page ID.
2. **Duplicate Titles:** A single page will have multiple rows if it is assessed by multiple WikiProjects. Use `GROUP_CONCAT` if you want a single row per article.
3. **Normalization:** Ratings are strings. Be aware that some projects use non-standard classes (e.g., "Future", "Current", or "Draft").
4. **Case Sensitivity:** WikiProject titles in the `pap_project_title` column are case-sensitive. "medicine" will fail; "Medicine" will succeed.

### **Example Use Cases for Agent**

* "Find all 'Featured Articles' in the 'Computing' WikiProject."
* "Identify high-importance stubs that need immediate expansion."
* "Compare the average quality of articles in 'WikiProject Maryland' versus 'WikiProject Virginia'."

### Recommended Resources

* **[MediaWiki: PageAssessments Extension](https://www.mediawiki.org/wiki/Extension:PageAssessments)** – The official documentation explaining how the data is parsed and stored.
* **[WikiTech: Page Assessments Table Schema](https://www.google.com/search?q=https://wikitech.wikimedia.org/wiki/Analytics/Data_Lake/MediaWiki/Page_assessments)** – Detailed breakdown of every column and how it relates to the Analytics Data Lake.
* **[English Wikipedia: Content Assessment]()** – Essential for understanding what the "Class" (FA, GA, B, etc.) and "Importance" values actually mean in the context of the community.
