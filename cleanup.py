from database import projects_collection

result = projects_collection.delete_many({
    'title': {'$in': ['Solar Panel Installation', 'Data Dashboard Project', 'AI Matching System']}
})

print('Deleted:', result.deleted_count)
print('Remaining:', projects_collection.count_documents({}))