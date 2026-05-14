## **Take-Home Brief: AI Engineer (Product Engineer Track)**

### **The Problem**

Minder AI is building a voice-first co-worker agent that lives inside factories. The agent needs to know everything a senior worker knows — the written procedures, the unwritten domain knowledge, the company policies, the tribal wisdom that floor workers accumulate over years and never document.

We have a clear path to ingesting the *written* knowledge: SOPs, training manuals, policy documents. That part is solved.

The hard problem is the **unwritten** knowledge. The senior welder knows that station 3 always overheats on Tuesdays after lunch and you need to drop the current by 5%. The 10-year laundry worker knows that polyester from Hotel A always shrinks if you run it on the same cycle as cotton. None of this is in any document. It lives in workers' heads and surfaces only in conversation — when someone asks a question, when something goes wrong, when a worker corrects the agent.

**Your job:** design a system where the agent learns from these conversations automatically. Every time a worker corrects the agent, teaches it something new, or reveals knowledge that was not in the original documents, the system captures it, verifies it, integrates it into a **shared knowledge base**, and serves it back to all workers in subsequent conversations.

This is the difference between an agent that knows what HR wrote down and an agent that knows what the factory actually does. The second one is the moat. The first one is a wrapper.

### **The Real Problem You Are Solving**

It is easy to extract facts from a transcript. LLMs do this in one prompt. The hard part is everything that comes after:

* **How do you know the extracted "fact" is actually true?** A worker might be wrong, joking, venting, or testing the agent. Half the conversation is noise.  
* **How do you reconcile contradictions?** Worker A says the dryer runs at 80°C. Worker B says 75°C. The SOP says 78°C. Who wins?  
* **How do you avoid the system poisoning itself?** If the agent learns from a wrong correction once, it will confidently repeat the wrong answer to the next worker, who may correct it again, and now you have noise feeding noise.  
* **How do you make this work in production?** The latency budget for retrieval is sub-second. Cost per conversation cannot exceed pennies. The factory has 50 workers having 200 conversations a day.  
* **How do you prove it is learning?** "The agent got better" is a vibe. We need a measurable signal.

A solution that handles extraction beautifully but ignores the verification, conflict, and poisoning problems is not a viable solution. It is a demo.

### **The Three Sub-Problems**

You must address all three. How you weigh them is your choice and part of the test.

#### **1\. Knowledge Acquisition**

Raw conversational data → structured, retrievable knowledge.

You decide: semantic parsing, knowledge graph, vector store updates, hybrid, something else entirely. Defend your data model. Defend why your representation supports the next two sub-problems and not just retrieval.

#### **2\. Consistency and Integration**

New knowledge meets existing knowledge. Sometimes they agree, sometimes they conflict, often they overlap ambiguously.

You decide the verification logic, the conflict resolution strategy, and the rules for what gets accepted, what gets quarantined, and what gets escalated to a human. There is no right answer. There are defensible answers and indefensible ones.

#### **3\. Feedback Loop**

Integrated knowledge → deployed to the agent → measurable improvement in subsequent conversations.

You decide what "improvement" means and how you measure it. If you cannot measure it, you cannot prove the system works.

### **A Note from Celesnity**

Approach this problem as if it were your own. Do not optimize for pleasing us or completing every task we listed. Optimise for solving the actual technical challenge in a way you would be willing to defend in production. That is what we hire for.

### **Suggested Reading**

To inspire your thinking, not to copy from. We are not testing whether you can re-implement these — we are testing whether you can reason about the same class of problems.

* **Memory and self-improving agents:** the public literature on Generative Agents (Park et al., Stanford), MemGPT, and Reflexion.  
* **Knowledge integration:** GraphRAG (Microsoft Research), Self-RAG, and the body of work on continual learning without catastrophic forgetting.  
* **Evaluation and self-improvement loops:** literature on LLM-as-judge, DSPy's optimisation framework, and constitutional AI feedback loops.  
* **Production agent architectures:** any well-documented open-source agent framework you respect — be ready to defend why you chose to follow or ignore its patterns.  
* **LLM Wiki:** approaches for building continuously evolving knowledge repositories around LLMs — including entity extraction, semantic linking, temporal memory, retrieval indexing, provenance tracking, and human-in-the-loop correction workflows. Think beyond “chat history” and toward systems that accumulate operational knowledge over months or years.

You are not required to use any of these. You are required to know the landscape well enough to defend your choices.

