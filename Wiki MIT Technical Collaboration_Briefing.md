### **POSSIBLE API**

### 

Claim: possible context or Wikipedia article 

### **API Name: Wiki\_MIT Matchmaker**

**Base URL**: https://mitocwmatch.toolforge.org/v1 (Proposed)

---

### **1\. Endpoints**

#### **POST /match/article**

**Description**: Takes a Wikipedia article title or raw string and returns a ranked list of relevant MIT OCW courses, modules, or specific files.

* **Request Parameters**:  
  1. article\_title (string): The title of the English Wikipedia article.  
  2. lang (string, default: "en"): The language code.  
  3. include\_sections (boolean, optional): Whether to provide matches for individual sections of the article.  
  4. min\_similarity (float, 0.0–1.0): Threshold for the cosine similarity score.  
* **Possible Internal Workflow**:  
  1. **Topic Routing**: Use the **Lift Wing API** (outlink-topic-model) to predict the article's broad subject area (e.g., "Physics" or "Biology") to filter the initial MIT course search space.  
  2. **Content Extraction**: Fetch article content via the **MediaWiki Action API** (prop=revisions).  
  3. **Semantic Search**: Map the article's content into a shared "latent space" using vector embeddings.  
  4. **Matchmaking**: Query the **MIT Learn API** (/learning\_resources/{id}/vector\_similar/) or a pre-computed vector database of MIT "atomic knowledge units".

#### **POST /match/claim**

**Description**: Takes a specific sentence or claim and finds relevant MIT materials to verify, prove, or expand upon it.

* **Request Parameters**:  
  1. claim\_text (string): A single sentence or paragraph.  
  2. resource\_type (array, optional): Filter by video, pdf, diagram, or lecture\_notes.  
* **Possible Internal Workflow**:  
  1. **Multimodal Vectorization**: Convert the claim into a high-dimensional vector.  
  2. **Cosine Similarity**: Measure the semantic "angle" between the claim and MIT course transcripts, slide deck text, and metadata.  
  3. **Deep-Linking**: Generate **timestamped links** (e.g., ?t=342s) for video matches to minimize editor friction.

---

### **2\. Response Format (JSON)**

The API returns a ranked list of Match objects.

JSON  
{  
  "query": "The Schwarzschild radius is the radius of a sphere such that...",  
  "matches": \[  
    {  
      "title": "General Relativity",  
      "course\_id": "8.033",  
      "similarity\_score": 0.942,  
      "url": "https://ocw.mit.edu/courses/8-033-general-relativity-fall-2006/",  
      "deep\_link": "https://ocw.mit.edu/resources/res-8-005-video-lectures/lecture-15/\#?t=210s",  
      "resource\_type": "video\_snippet",  
      "snippet": "In this section, we derive the Schwarzschild metric for a non-rotating mass...",  
      "suggested\_action": "{{Refideas |item1=\[URL\] |comment=Detailed derivation of the Schwarzschild radius provided in Lecture 15 of MIT 8.033.}}"  
    }  
  \]  
}  
