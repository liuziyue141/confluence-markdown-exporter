# Multi-Tenant RAG Integration Plan

## 🔍 **Current RAG Implementation Analysis**

### **Current Architecture Issues**
```python
# ❌ HARDCODED - Not multi-tenant ready
MARKDOWN_EXPORT_PATH = "/Users/lindalee/confluence_exp"
COLLECTION_NAME = "postgres/confluence_parent_docs"
CONNECTION_STRING = "postgresql+psycopg://tim_itagent:Apple3344!@localhost:5432/confluence_exp"
```

### **Key Components to Make Multi-Tenant**
1. **`SmartParentDocumentRAG`** - Currently uses fixed paths and collection names
2. **`DocumentManager`** - Needs customer-aware operations
3. **`ParentDocumentRetriever`** - Needs customer-specific vector stores
4. **PGVector Collections** - Needs unique collection names per customer

### **Current Workflow (Single-Tenant)**
```
Fixed Path → Load Docs → Process → Single Collection → Global Retriever
```

---

## 🎯 **Multi-Tenant RAG Requirements**

### **Data Isolation Requirements**
1. **Vector Store Isolation**: Each customer gets separate PGVector collection
2. **Document Store Isolation**: Each customer's documents stored separately  
3. **Retriever Isolation**: Each customer gets their own retriever instance
4. **Configuration Isolation**: Customer-specific RAG settings

### **Performance Requirements**
1. **Efficient Retrieval**: Fast customer-specific queries
2. **Scalable Indexing**: Handle multiple customers concurrently
3. **Memory Efficiency**: Don't load all customers' data at once
4. **Connection Pooling**: Efficient database connections

### **Integration Requirements**
1. **Workflow Integration**: Export → Index → Query pipeline
2. **Configuration Integration**: RAG settings in `CustomerConfig`
3. **State Management**: Track RAG status per customer
4. **Error Handling**: Customer-specific error isolation

---

## 🏗️ **Proposed Multi-Tenant Architecture**

### **Collection Naming Strategy**
```python
# Customer-specific collection names to prevent conflicts
COLLECTION_NAME_TEMPLATE = "customer_{customer_id}_documents"

# Examples:
# customer_acme_corp_documents
# customer_tech_startup_documents  
# customer_itagent_documents
```

### **Customer Configuration Extension**
```python
# Add to CustomerConfig in shared/models.py
class RAGConfig(BaseModel):
    vector_store_path: Path
    collection_name: str
    connection_string: str
    enable_parent_retriever: bool = True
    chunk_size: int = 1000
    chunk_overlap: int = 100
    parent_chunk_size: int = 50000
    embedding_model: str = "gemini-embedding-001"
    
class CustomerConfig(BaseModel):
    # ... existing fields ...
    rag: RAGConfig
```

### **New Class: CustomerRAGManager**
```python
class CustomerRAGManager:
    """
    Customer-aware RAG system with complete data isolation.
    
    Key Features:
    - Customer-specific vector collections
    - Isolated document processing  
    - Parent document retrieval per customer
    - Incremental indexing with change detection
    """
    
    def __init__(self, customer_config: CustomerConfig)
    def build_index(self, export_path: Path) -> Dict
    def update_index(self, export_path: Path) -> Dict  
    def get_retriever(self) -> ParentDocumentRetriever
    def query(self, question: str, top_k: int = 3) -> List[Document]
    def get_stats(self) -> Dict
    def cleanup_index(self) -> bool
```

---

## 📊 **Integration Architecture**

### **Updated Customer Directory Structure**
```
data/customers/{customer_id}/
├── config.yaml              # Customer configuration + RAG settings
├── state.json               # Operational state + RAG status
├── exports/                 # Exported markdown files (SOURCE for RAG)
│   └── {space_name}/        
├── cache/                   # Export tracking
├── vectors/                 # RAG-specific data
│   ├── index_cache.json     # RAG indexing cache
│   └── rag_results/         # RAG operation results
└── logs/                    # Customer logs
```

### **Extended Customer State**
```python
class CustomerState(BaseModel):
    # ... existing fields ...
    
    # RAG-specific state
    rag_status: RAGStatus = RAGStatus.NEVER_BUILT
    last_index_time: Optional[datetime] = None
    total_indexed_documents: int = 0
    total_indexed_chunks: int = 0
    rag_collection_name: str = ""
    is_ready_for_queries: bool = False
```

---

## 🔄 **Integrated Workflow Design**

### **Phase 1: Export + Index Pipeline**
```python
# Unified workflow: Export → Index
class ExportManager:
    def __init__(self, customer_config: CustomerConfig):
        self.exporter = SpaceExporter(customer_config)
        self.rag_manager = CustomerRAGManager(customer_config)  # NEW
    
    def export_and_index(self, space_keys: List[str] = None) -> Dict:
        """Complete workflow: Export spaces then build RAG index"""
        # 1. Export spaces
        export_result = self.export(space_keys)
        
        # 2. Build/update RAG index if export successful
        if export_result.status in [ExportStatus.COMPLETED, ExportStatus.PARTIAL]:
            rag_result = self.rag_manager.update_index(self.customer_config.export.output_path)
            
        return {
            'export_result': export_result,
            'rag_result': rag_result
        }
```

### **Phase 2: Query Pipeline**
```python
class CustomerQueryManager:
    """
    Handle customer-specific RAG queries with retrieval optimization.
    """
    
    def __init__(self, customer_config: CustomerConfig):
        self.rag_manager = CustomerRAGManager(customer_config)
        self.retriever = self.rag_manager.get_retriever()
        
    def query(self, question: str) -> QueryResult:
        """Execute customer-specific RAG query"""
        # Uses customer's isolated vector collection
        documents = self.retriever.get_relevant_documents(question)
        return QueryResult(
            customer_id=self.customer_config.customer_id,
            question=question,
            documents=documents,
            collection_used=self.rag_manager.collection_name
        )
```

---

## 🛠️ **Implementation Strategy**

### **Step 1: Extend Configuration Models** ⏱️ 30 min
- [ ] Add `RAGConfig` to `shared/models.py`
- [ ] Update `CustomerConfig` to include `rag: RAGConfig`
- [ ] Add RAG status fields to `CustomerState`
- [ ] Update customer creation to generate RAG config

### **Step 2: Create CustomerRAGManager** ⏱️ 2 hours
- [ ] Create `confluence_rag_integration/rag/customer_rag_manager.py`
- [ ] Implement customer-specific collection naming
- [ ] Port `SmartParentDocumentRAG` logic with customer isolation
- [ ] Add customer-specific document processing
- [ ] Implement retriever factory per customer

### **Step 3: Create RAG Integration Classes** ⏱️ 1 hour
- [ ] Create `confluence_rag_integration/rag/query_manager.py`
- [ ] Create customer-aware query pipeline
- [ ] Add query result models
- [ ] Implement query history tracking

### **Step 4: Integrate with ExportManager** ⏱️ 1 hour
- [ ] Add RAG manager to `ExportManager.__init__()`
- [ ] Create `export_and_index()` method
- [ ] Add RAG status tracking
- [ ] Update customer state management

### **Step 5: Update Customer Management** ⏱️ 30 min
- [ ] Update `CustomerManager.create_customer()` to include RAG config
- [ ] Add RAG status update methods
- [ ] Create customer RAG validation

### **Step 6: Create RAG API Layer** ⏱️ 1 hour
- [ ] Create unified RAG interface
- [ ] Add customer query endpoint
- [ ] Implement RAG monitoring
- [ ] Add performance tracking

---

## 🚨 **Critical Design Decisions**

### **Collection Naming & Uniqueness**
```python
def generate_collection_name(customer_id: str) -> str:
    """Generate unique, safe collection name for customer"""
    # Sanitize customer_id for database safety
    safe_id = re.sub(r'[^a-zA-Z0-9_]', '_', customer_id.lower())
    return f"customer_{safe_id}_documents"

# Examples:
# customer_acme_corp_documents
# customer_tech_startup_documents
# customer_itagent_documents
```

### **Connection Management**
```python
# Option A: Shared connection, separate collections (RECOMMENDED)
CONNECTION_STRING = "postgresql+psycopg://user:pass@localhost:5432/confluence_rag"
# Each customer gets unique collection in same database

# Option B: Separate databases per customer (if extreme isolation needed)
# CONNECTION_TEMPLATE = "postgresql+psycopg://user:pass@localhost:5432/customer_{customer_id}"
```

### **Memory & Performance Optimization**
```python
# Lazy loading: Don't load all customer RAG systems at startup
class RAGFactory:
    """Factory for creating customer-specific RAG managers on demand"""
    
    _instances: Dict[str, CustomerRAGManager] = {}
    
    @classmethod
    def get_rag_manager(cls, customer_config: CustomerConfig) -> CustomerRAGManager:
        """Get or create RAG manager for customer (with caching)"""
        customer_id = customer_config.customer_id
        
        if customer_id not in cls._instances:
            cls._instances[customer_id] = CustomerRAGManager(customer_config)
            
        return cls._instances[customer_id]
```

---

## 🎯 **Expected Benefits**

### **Data Isolation**
- ✅ **Complete Separation**: Each customer's vectors in separate collections
- ✅ **No Data Leakage**: Impossible for customer A to see customer B's data
- ✅ **Independent Scaling**: Each customer's RAG can scale independently

### **Performance**
- ✅ **Faster Queries**: Customer-specific collections are smaller and faster
- ✅ **Parallel Processing**: Multiple customers can build indexes simultaneously
- ✅ **Efficient Memory**: Only load needed customer data

### **Operational**
- ✅ **Customer-Specific Monitoring**: Track RAG performance per customer
- ✅ **Independent Updates**: Update one customer's index without affecting others
- ✅ **Flexible Configuration**: Each customer can have different RAG settings

---

## 📋 **Integration Checklist**

### **Configuration Integration**
- [ ] RAG settings in customer config
- [ ] Customer-specific collection names
- [ ] Database connection management
- [ ] RAG status in customer state

### **Workflow Integration**
- [ ] Export → Index pipeline
- [ ] Incremental index updates
- [ ] Query → Results pipeline
- [ ] Error handling and recovery

### **API Integration**
- [ ] Customer query endpoints
- [ ] RAG status endpoints
- [ ] Index management endpoints
- [ ] Performance monitoring

### **Testing & Validation**
- [ ] Multi-customer RAG isolation
- [ ] Concurrent indexing operations
- [ ] Query performance per customer
- [ ] Data leakage prevention

---

## 🚀 **Next Steps**

### **Immediate Actions**
1. **Start with Step 1**: Extend configuration models
2. **Create CustomerRAGManager**: Core customer-aware RAG functionality
3. **Test with Single Customer**: Validate isolation works
4. **Integrate with ExportManager**: Complete export→index workflow

### **Phase 2 Goals**
- Multi-customer RAG queries working
- Complete data isolation verified  
- Performance benchmarks established
- Production-ready customer onboarding

**Total Estimated Time**: ~6 hours for complete multi-tenant RAG integration

**Status**: 🟡 **Ready to Implement** - Architecture planned, implementation steps defined! 
