# 前端 Dockerfile
FROM node:18-alpine

WORKDIR /app

# 复制 package.json 和 package-lock.json
COPY package*.json ./

# 安装依赖
RUN npm install

# 复制项目文件
COPY . .

EXPOSE 5173

# 开发模式启动
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
